import XCTest
@testable import AudiobookStudio

final class BridgeTests: XCTestCase {
    func testSwiftSettingsRoundTripThroughPythonStatus() throws {
        let repo = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let project = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: project) }
        var config = BookSettings()
        config.title = "Bridge test"
        config.source = "/tmp/test.epub"
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        try encoder.encode(config).write(to: project.appendingPathComponent("book.json"))
        try Data("[]".utf8).write(to: project.appendingPathComponent("chapters.json"))
        let process = Process(); let input = Pipe(); let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [repo.appendingPathComponent("app_bridge.py").path]
        process.standardInput = input; process.standardOutput = output
        try process.run()
        try input.fileHandleForWriting.write(contentsOf: encoder.encode(BridgeRequest(action: "status", project: project.path, config: nil)))
        try input.fileHandleForWriting.close()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(BridgeResponse.self, from: data)
        XCTAssertTrue(response.ok, response.error ?? "")
        XCTAssertEqual(response.config?.ceilingC, 90)
        XCTAssertEqual(response.config?.gpuCeilingC, 93)
        XCTAssertEqual(response.config?.gpuPauseC, 89)
        XCTAssertEqual(response.config?.gpuResumeC, 85)
        XCTAssertEqual(response.config?.title, "Bridge test")
        XCTAssertEqual(response.config?.speed, 1.25)
        XCTAssertEqual(response.config?.paragraphGap, 0.2)
        XCTAssertEqual(response.progress?.saved, 0)
        XCTAssertEqual(response.active, false)
        XCTAssertEqual(response.complete, false)
    }
}
