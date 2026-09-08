// Kord's native macOS shell.
//
// This used to be a shell script that started the server and called `open`,
// which handed the user a browser tab. That is not an app: it has no window of
// its own, no dock icon that means anything, and quitting the browser leaves
// the server running. This replaces it with a real windowed application that
// owns its server's lifetime and hosts the UI in a WKWebView, the way any
// other locally-installed Mac app behaves.

import Cocoa
import WebKit

// MARK: - Locating the bundle's own copies of everything

let resources = Bundle.main.resourceURL!
let python = resources.appendingPathComponent("python/bin/python3")
let home = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Kord")
let logURL = home.appendingPathComponent("kord.log")

func log(_ message: String) {
    let line = "[\(ISO8601DateFormatter().string(from: Date()))] \(message)\n"
    guard let data = line.data(using: .utf8) else { return }
    if let handle = try? FileHandle(forWritingTo: logURL) {
        handle.seekToEndOfFile()
        handle.write(data)
        try? handle.close()
    } else {
        try? data.write(to: logURL)
    }
}

/// A port nothing else is listening on. Kord picks one per launch rather than
/// hardcoding 8000, so a second copy — or anything else already on that port —
/// cannot make the app come up to a blank window.
func freePort() -> UInt16 {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { return 8000 }
    defer { close(fd) }
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_addr.s_addr = inet_addr("127.0.0.1")
    addr.sin_port = 0
    let bound = withUnsafePointer(to: &addr) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    guard bound == 0 else { return 8000 }
    var out = sockaddr_in()
    var len = socklen_t(MemoryLayout<sockaddr_in>.size)
    let got = withUnsafeMutablePointer(to: &out) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            getsockname(fd, $0, &len)
        }
    }
    guard got == 0 else { return 8000 }
    return UInt16(bigEndian: out.sin_port)
}

// MARK: - The app

final class Kord: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var splash: NSView!
    var status: NSTextField!
    var children: [Process] = []
    let port = freePort()
    var base: String { "http://127.0.0.1:\(port)" }

    func applicationDidFinishLaunching(_ note: Notification) {
        try? FileManager.default.createDirectory(
            at: home.appendingPathComponent("models"), withIntermediateDirectories: true)
        log("--- Kord starting on port \(port) ---")

        buildMenu()
        buildWindow()
        copyBundledModel()
        startServer()
        waitForServer()
    }

    // Without an Edit menu the webview gets no Cut/Copy/Paste/Select-All key
    // equivalents, so the search box would silently ignore ⌘V.
    func buildMenu() {
        let bar = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About Kord", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide Kord", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Kord", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        bar.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        bar.addItem(editItem)

        let viewItem = NSMenuItem()
        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r")
        view.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        view.addItem(.separator())
        view.addItem(withTitle: "Show Log in Finder", action: #selector(showLog), keyEquivalent: "")
        viewItem.submenu = view
        bar.addItem(viewItem)

        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        windowItem.submenu = windowMenu
        bar.addItem(windowItem)
        NSApp.windowsMenu = windowMenu

        NSApp.mainMenu = bar
    }

    func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1180, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered, defer: false)
        window.title = "Kord"
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 900, height: 600)
        window.setFrameAutosaveName("KordWindow")
        window.center()
        window.backgroundColor = NSColor(red: 0.05, green: 0.05, blue: 0.07, alpha: 1)

        let config = WKWebViewConfiguration()
        // Stems are played back with an <audio> element the page starts itself;
        // requiring a gesture per element would break playback entirely.
        config.mediaTypesRequiringUserActionForPlayback = []
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.isHidden = true
        window.contentView!.addSubview(webView)

        splash = NSView(frame: window.contentView!.bounds)
        splash.autoresizingMask = [.width, .height]
        splash.wantsLayer = true
        splash.layer?.backgroundColor = NSColor(red: 0.05, green: 0.05, blue: 0.07, alpha: 1).cgColor

        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.startAnimation(nil)
        spinner.frame = NSRect(x: splash.bounds.midX - 16, y: splash.bounds.midY, width: 32, height: 32)
        spinner.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        splash.addSubview(spinner)

        status = NSTextField(labelWithString: "Starting Kord…")
        status.alignment = .center
        status.textColor = NSColor(white: 0.65, alpha: 1)
        status.font = .systemFont(ofSize: 13)
        status.frame = NSRect(x: 0, y: splash.bounds.midY - 40, width: splash.bounds.width, height: 20)
        status.autoresizingMask = [.width, .minYMargin, .maxYMargin]
        splash.addSubview(status)

        window.contentView!.addSubview(splash)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// The chord model ships read-only in the bundle; Kord reads it from the
    /// user's data directory, so it is placed there once on first run.
    func copyBundledModel() {
        let src = resources.appendingPathComponent("models/btc_model_large_voca.pt")
        let dst = home.appendingPathComponent("models/btc_model_large_voca.pt")
        if FileManager.default.fileExists(atPath: src.path),
           !FileManager.default.fileExists(atPath: dst.path) {
            try? FileManager.default.copyItem(at: src, to: dst)
        }
    }

    func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["KORD_HOME"] = home.path
        env["KORD_UI_DIR"] = resources.appendingPathComponent("ui").path
        env["HF_HOME"] = resources.appendingPathComponent("hf").path
        env["KORD_UI_URL"] = base
        env["PATH"] = resources.appendingPathComponent("bin").path + ":" + (env["PATH"] ?? "/usr/bin:/bin")
        env.removeValue(forKey: "PYTHONHOME")   // never inherit a system Python
        env.removeValue(forKey: "PYTHONPATH")
        return env
    }

    func spawn(_ arguments: [String]) {
        let task = Process()
        task.executableURL = python
        task.arguments = arguments
        task.environment = environment()
        if let handle = try? FileHandle(forWritingTo: logURL) {
            handle.seekToEndOfFile()
            task.standardOutput = handle
            task.standardError = handle
        }
        do {
            try task.run()
            children.append(task)
        } catch {
            log("failed to start \(arguments): \(error)")
        }
    }

    func startServer() {
        spawn(["-m", "uvicorn", "kord.app:build_app", "--factory",
               "--host", "127.0.0.1", "--port", "\(port)"])
        spawn(["-m", "kord.queue"])
    }

    /// Poll until the API answers, then swap the splash for the UI. The first
    /// launch imports torch, which is slow enough that a fixed delay would be
    /// a guess — hence polling, with a deadline long enough for a cold start.
    func waitForServer(attempt: Int = 0) {
        let url = URL(string: base + "/api/health")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async {
                if ok {
                    log("server up after \(attempt) polls")
                    self.webView.load(URLRequest(url: URL(string: self.base)!))
                } else if attempt >= 240 {          // two minutes
                    self.failed()
                } else {
                    if attempt == 20 { self.status.stringValue = "Starting Kord… (first launch takes a moment)" }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self.waitForServer(attempt: attempt + 1)
                    }
                }
            }
        }.resume()
    }

    func failed() {
        status.stringValue = "Kord could not start. See kord.log for details."
        let button = NSButton(title: "Show Log", target: self, action: #selector(showLog))
        button.frame = NSRect(x: splash.bounds.midX - 60, y: splash.bounds.midY - 90, width: 120, height: 28)
        button.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        splash.addSubview(button)
        for view in splash.subviews.compactMap({ $0 as? NSProgressIndicator }) {
            view.stopAnimation(nil)
            view.isHidden = true
        }
    }

    @objc func reload() { webView.reload() }
    @objc func showLog() { NSWorkspace.shared.activateFileViewerSelecting([logURL]) }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        splash.isHidden = true
        webView.isHidden = false
    }

    // Anything that is not Kord's own server — a Spotify login, a help link —
    // belongs in the user's browser, not inside this window.
    func webView(_ webView: WKWebView,
                 decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != "127.0.0.1", !url.absoluteString.hasPrefix("about:") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // window.open() from the page has no window to open into; keep it in place.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    // Closing the window must stop the server too. The old launcher left
    // uvicorn and the worker running after the browser tab was closed.
    func applicationWillTerminate(_ note: Notification) {
        for task in children where task.isRunning { task.terminate() }
        log("--- Kord stopped ---")
    }
}

let app = NSApplication.shared
let delegate = Kord()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
