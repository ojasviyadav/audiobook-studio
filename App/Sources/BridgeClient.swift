import Foundation
import os

typealias BridgeOperation = @Sendable (BridgeRequest, String, String) async throws -> BridgeResponse

enum BridgeError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}

enum BridgeClient {
    static let performance = OSLog(subsystem: "local.ojasvi.audiobookstudio", category: "Performance")

    static func call(_ request: BridgeRequest, _ executable: String, _ repo: String) async throws -> BridgeResponse {
        try Task.checkCancellation()
        let id = OSSignpostID(log: performance)
        os_signpost(.begin, log: performance, name: "BridgeRequest", signpostID: id, "%{public}s", request.action)
        defer { os_signpost(.end, log: performance, name: "BridgeRequest", signpostID: id) }
        // A started command owns its process until it exits. UI cancellation does not kill narration.
        let response = try await Task.detached(priority: .utility) {
            guard FileManager.default.isExecutableFile(atPath: executable) else {
                throw BridgeError.message("Python runtime is missing or is not executable.")
            }
            guard FileManager.default.fileExists(atPath: repo + "/app_bridge.py") else {
                throw BridgeError.message("app_bridge.py is missing from the configured repository.")
            }
            let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
            let input = try encoder.encode(request)
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: folder) }
            let outURL = folder.appendingPathComponent("stdout"), errURL = folder.appendingPathComponent("stderr")
            FileManager.default.createFile(atPath: outURL.path, contents: nil)
            FileManager.default.createFile(atPath: errURL.path, contents: nil)
            let output = try FileHandle(forWritingTo: outURL), errors = try FileHandle(forWritingTo: errURL)
            defer { try? output.close(); try? errors.close() }
            let process = Process(), stdin = Pipe()
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = [repo + "/app_bridge.py"]
            process.currentDirectoryURL = URL(fileURLWithPath: repo)
            var environment = ProcessInfo.processInfo.environment
            environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            environment["OMP_NUM_THREADS"] = "1"
            process.environment = environment
            process.standardInput = stdin; process.standardOutput = output; process.standardError = errors
            try process.run()
            try stdin.fileHandleForWriting.write(contentsOf: input)
            try stdin.fileHandleForWriting.close()
            process.waitUntilExit()
            // Separate file handles prevent a full stderr pipe from blocking the engine.
            let data = try Data(contentsOf: outURL)
            let stderr = try String(contentsOf: errURL, encoding: .utf8)
            guard process.terminationStatus == 0, !data.isEmpty else {
                throw BridgeError.message("Bridge exit \(process.terminationStatus). \(stderr.suffix(4000))")
            }
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            let response = try decoder.decode(BridgeResponse.self, from: data)
            if !response.ok { throw BridgeError.message(response.error ?? "The engine returned an unspecified failure.") }
            return response
        }.value
        try Task.checkCancellation()
        return response
    }
}
