import Foundation
import os

struct ErrorContext: Codable, Sendable {
    let id: String
    let action: String
    let engine: String
}
struct Breadcrumb: Codable, Sendable {
    var time = Date()
    let action: String
}
protocol ErrorMonitoringService: Sendable {
    func captureError(_ error: any Error, context: ErrorContext) async
    func addBreadcrumb(_ breadcrumb: Breadcrumb) async
}
struct NoOpErrorMonitoring: ErrorMonitoringService {
    func captureError(_ error: any Error, context: ErrorContext) async {}
    func addBreadcrumb(_ breadcrumb: Breadcrumb) async {}
}

/// No remote provider, account, identity, request text, or book contents are collected.
/// Engine error details stay in a bounded local report, separate from user-facing messages.
actor LocalErrorMonitoring: ErrorMonitoringService {
    static let shared = LocalErrorMonitoring()
    static let directory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/Audiobook Studio")
    private let directory: URL
    private var breadcrumbs: [Breadcrumb] = []
    private let logger = Logger(subsystem: "local.ojasvi.audiobookstudio", category: "Errors")
    init(directory: URL = LocalErrorMonitoring.directory) { self.directory = directory }

    func addBreadcrumb(_ breadcrumb: Breadcrumb) {
        breadcrumbs.append(breadcrumb)
        breadcrumbs = Array(breadcrumbs.suffix(20))
    }

    func captureError(_ error: any Error, context: ErrorContext) {
        struct Report: Encodable {
            var time = Date()
            let context: ErrorContext
            let details: String
            let breadcrumbs: [Breadcrumb]
            let version: String
        }
        let report = Report(context: context, details: String(error.localizedDescription.prefix(8000)),
                            breadcrumbs: breadcrumbs, version: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "test")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                   attributes: [.posixPermissions: 0o700])
            let url = directory.appendingPathComponent("errors.jsonl")
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            var data = try encoder.encode(report); data.append(10)
            let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            if size + data.count > 1_000_000 {
                let old = directory.appendingPathComponent("errors-previous.jsonl")
                if FileManager.default.fileExists(atPath: old.path) { try FileManager.default.removeItem(at: old) }
                try FileManager.default.moveItem(at: url, to: old)
            }
            if !FileManager.default.fileExists(atPath: url.path) {
                FileManager.default.createFile(atPath: url.path, contents: nil, attributes: [.posixPermissions: 0o600])
            }
            let handle = try FileHandle(forWritingTo: url)
            defer { try? handle.close() }
            try handle.seekToEnd(); try handle.write(contentsOf: data)
            logger.error("Report \(context.id, privacy: .public), action \(context.action, privacy: .public)")
        } catch {
            logger.error("Cannot write diagnostic report: \(error.localizedDescription, privacy: .private)")
        }
    }
}

enum UserFacingFailure {
    static func message(for action: String) -> String {
        switch action {
        case "load": return "This project could not be opened. Check that you selected a conversion folder."
        case "status": return "Progress could not be checked. The recording may still be running. Retrying shortly."
        case "prepare": return "The book could not be prepared or started. Check the EPUB and engine setup. Saved audio is kept."
        case "preview": return "The sample could not be made or played. Check engine setup and try again when no book is running."
        case "download", "install", "check": return "Engine setup could not finish. Check the paths in Setup and the internet connection."
        case "save": return "These settings could not be saved. Check the temperature limits. Saved audio keeps its original voice and pace."
        case "logs": return "The conversion log could not be opened. Check the project folder."
        default: return "The conversion command could not finish. Refresh the status before you try again. Saved audio is kept."
        }
    }
}
