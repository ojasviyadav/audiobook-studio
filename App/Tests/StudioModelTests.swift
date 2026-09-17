import XCTest
@testable import AudiobookStudio

actor ControlledBridge {
    var requests: [BridgeRequest] = []
    var pending: [Int: CheckedContinuation<BridgeResponse, any Error>] = [:]
    var observers: [(Int, CheckedContinuation<Void, Never>)] = []
    let blocked: Set<String>
    let initial: BridgeResponse
    init(blocked: Set<String>, initial: BridgeResponse) { self.blocked = blocked; self.initial = initial }
    func call(_ request: BridgeRequest) async throws -> BridgeResponse {
        let index = requests.count
        requests.append(request)
        if blocked.contains(request.action) {
            return try await withCheckedThrowingContinuation { continuation in
                pending[index] = continuation
                notify()
            }
        }
        notify()
        return initial
    }
    func notify() {
        let ready = observers.filter { requests.count >= $0.0 }
        observers.removeAll { requests.count >= $0.0 }
        for (_, continuation) in ready { continuation.resume() }
    }
    func waitForCalls(_ count: Int) async {
        if requests.count >= count { return }
        await withCheckedContinuation { observers.append((count, $0)) }
    }
    func reply(_ index: Int, _ response: BridgeResponse) { pending.removeValue(forKey: index)?.resume(returning: response) }
    func fail(_ index: Int) { pending.removeValue(forKey: index)?.resume(throwing: BridgeError.message("Traceback SECRET /Users/private/book.txt")) }
}
actor RecordingMonitor: ErrorMonitoringService {
    var reports: [ErrorContext] = []
    func captureError(_ error: any Error, context: ErrorContext) { reports.append(context) }
    func addBreadcrumb(_ breadcrumb: Breadcrumb) {}
}

@MainActor
final class StudioModelTests: XCTestCase {
    func savedBook(complete: Bool = true) -> BridgeResponse {
        var settings = BookSettings()
        settings.source = "/tmp/Emotional Design.epub"; settings.backend = "kokoro"
        settings.voice = "af_heart"; settings.speed = 0.95
        return BridgeResponse(ok: true, config: settings,
            progress: ProgressInfo(saved: 100, total: 100, percent: 100, audioSeconds: 100, sections: []),
            active: false, complete: complete)
    }
    func model(_ bridge: ControlledBridge, monitor: any ErrorMonitoringService = NoOpErrorMonitoring()) -> StudioModel {
        let model = StudioModel(bridge: { request, _, _ in try await bridge.call(request) }, monitoring: monitor)
        model.project = "/tmp/saved-book"
        return model
    }
    func waitUntilIdle(_ model: StudioModel) async {
        for _ in 0..<2000 {
            if !model.busy { return }
            await Task.yield()
        }
        XCTFail("Action did not finish")
    }
    func testSavedKokoroIsTruthfulAndNewQwenVersionKeepsSource() async {
        let bridge = ControlledBridge(blocked: [], initial: savedBook())
        let model = model(bridge)
        await model.loadProject()
        XCTAssertEqual(model.settings.backend, "kokoro")
        XCTAssertTrue(model.narrationContext.contains("Saved recording: Heart · Kokoro · 0.95×"))
        XCTAssertEqual(model.defaultNarration, "New books: Qwen · Ryan · 1.25×")
        let oldProject = model.project
        model.newQwenVersion()
        XCTAssertEqual(model.settings.backend, "qwen")
        XCTAssertEqual(model.settings.voice, "Ryan")
        XCTAssertEqual(model.settings.speed, 1.25)
        XCTAssertEqual(model.settings.source, "/tmp/Emotional Design.epub")
        XCTAssertNotEqual(model.project, oldProject)
        XCTAssertFalse(model.prepared)
        XCTAssertNil(model.snapshot)
        let requests = await bridge.requests
        XCTAssertEqual(requests.map(\.action), ["load"], "Making a draft must not generate or overwrite audio")
    }
    func testOldStatusCannotReplaceNewProjectAndChecksDoNotOverlap() async {
        let bridge = ControlledBridge(blocked: ["status"], initial: savedBook())
        let model = model(bridge)
        await model.loadProject()
        let oldRefresh = Task { await model.refresh() }
        await bridge.waitForCalls(2)
        await model.refresh()
        model.newQwenVersion()
        await bridge.reply(1, savedBook())
        await oldRefresh.value
        XCTAssertNil(model.snapshot)
        XCTAssertEqual(model.settings.backend, "qwen")
        let requests = await bridge.requests
        XCTAssertEqual(requests.count, 2)
    }
    func testOldFailureCannotShowInNewProject() async {
        let monitor = RecordingMonitor()
        let bridge = ControlledBridge(blocked: ["status"], initial: savedBook())
        let model = model(bridge, monitor: monitor)
        await model.loadProject()
        let refresh = Task { await model.refresh() }
        await bridge.waitForCalls(2)
        model.newBook()
        await bridge.fail(1)
        await refresh.value
        XCTAssertNil(model.error)
        XCTAssertFalse(model.notice.contains("SECRET"))
        let reports = await monitor.reports
        XCTAssertTrue(reports.isEmpty)
    }
    func testCommandOwnsProjectUntilCompletionAndRejectsDuplicate() async {
        let bridge = ControlledBridge(blocked: ["preview"], initial: savedBook())
        let model = model(bridge)
        model.settings.source = "/tmp/book.epub"
        model.perform("preview")
        await bridge.waitForCalls(1)
        let path = model.project
        model.newBook(); model.newQwenVersion(); model.selectEngine("kokoro"); model.perform("preview")
        XCTAssertTrue(model.busy)
        XCTAssertEqual(model.project, path)
        XCTAssertEqual(model.settings.backend, "qwen")
        await bridge.reply(0, BridgeResponse(ok: true, message: "Sample ready"))
        await waitUntilIdle(model)
        let requests = await bridge.requests
        XCTAssertEqual(requests.map(\.action), ["preview"])
        model.newBook()
        XCTAssertEqual(model.project, "")
    }
    func testCompletedBookDoesNotPollAndCancelledStatusIsIgnored() async {
        let bridge = ControlledBridge(blocked: ["status"], initial: savedBook())
        let model = model(bridge)
        await model.loadProject()
        XCTAssertFalse(model.shouldPoll)
        await model.poll()
        let refresh = Task { await model.refresh() }
        await bridge.waitForCalls(2)
        refresh.cancel()
        await bridge.reply(1, BridgeResponse(ok: true, complete: false))
        await refresh.value
        XCTAssertTrue(model.complete)
        let requests = await bridge.requests
        XCTAssertEqual(requests.map(\.action), ["load", "status"])
    }
    func testFailureHasSafeMessageAndDiagnosticReference() async {
        let monitor = RecordingMonitor()
        let bridge = ControlledBridge(blocked: ["check"], initial: savedBook())
        let model = model(bridge, monitor: monitor)
        model.perform("check")
        await bridge.waitForCalls(1)
        await bridge.fail(0)
        await waitUntilIdle(model)
        XCTAssertFalse(model.error?.contains("SECRET") ?? true)
        XCTAssertFalse(model.error?.contains("Traceback") ?? true)
        XCTAssertTrue(model.error?.contains("Report:") ?? false)
        let reports = await monitor.reports
        XCTAssertEqual(reports.first?.id, model.diagnosticsID)
        XCTAssertEqual(reports.first?.action, "check")
    }
    func testLocalReportIncludesBoundedBreadcrumbs() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let monitor = LocalErrorMonitoring(directory: directory)
        for _ in 0..<30 { await monitor.addBreadcrumb(Breadcrumb(action: "status")) }
        await monitor.captureError(BridgeError.message("engine exit 13"), context: ErrorContext(id: "TEST", action: "preview", engine: "qwen"))
        let data = try Data(contentsOf: directory.appendingPathComponent("errors.jsonl"))
        let report = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual((report["breadcrumbs"] as? [Any])?.count, 20)
        XCTAssertEqual(report["details"] as? String, "engine exit 13")
    }
}

import SwiftUI
extension StudioModelTests {
    func testRenderPublicAppLayout() throws {
        guard let output = ProcessInfo.processInfo.environment["STUDIO_LAYOUT_PATH"] else { return }
        let bridge = ControlledBridge(blocked: [], initial: BridgeResponse(ok: true))
        let model = model(bridge)
        model.newBook()
        let view = NSHostingView(rootView: StudioView(model: model)
            .frame(width: 1100, height: 900)
            .tint(StudioPalette.accent).groupBoxStyle(StudioCardStyle())
            .environment(\.colorScheme, .dark))
        view.frame = NSRect(x: 0, y: 0, width: 1100, height: 900)
        view.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: URL(fileURLWithPath: output))
    }
}
