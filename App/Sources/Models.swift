import Foundation
import AppKit
import Combine
import AVFoundation

struct BookSettings: Codable, Sendable {
    var title = ""
    var author = ""
    var source = ""
    var modelDir = ""
    var sensorDir = ""
    var outputName = "Audiobook.m4b"
    var cover: String? = nil
    var voice = "af_heart"
    var speed = 0.95
    var bitrate = 96
    var paragraphGap = 0.2
    var chapterGap = 1.0
    var segmentRest = 0.5
    var ceilingC = 90.0
    var pauseC = 86.0
    var resumeC = 82.0
    var workSeconds = 60.0
    var restSeconds = 5.0
    var stableSeconds = 1.0
}
struct SectionProgress: Decodable, Sendable, Identifiable {
    var title: String
    var done: Int
    var total: Int
    var id: String { title }
}
struct ProgressInfo: Decodable, Sendable {
    var saved: Int
    var total: Int
    var percent: Double
    var audioSeconds: Double
    var etaSeconds: Double?
    var sections: [SectionProgress]
}
struct ThermalInfo: Decodable, Sendable {
    var cpuMaxC: Double?
    var gpuMaxC: Double?
    var userTargetC: Double?
    var running: Bool?
    var error: String?
    var time: Double?
}
struct BridgeResponse: Decodable, Sendable {
    var ok: Bool
    var error: String?
    var message: String?
    var config: BookSettings?
    var progress: ProgressInfo?
    var thermal: ThermalInfo?
    var active: Bool?
    var legacy: Bool?
    var paused: Bool?
    var complete: Bool?
    var phase: String?
    var output: String?
    var log: String?
}
struct BridgeRequest: Encodable, Sendable {
    var action: String
    var project: String
    var config: BookSettings?
}
enum BridgeError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}

@MainActor
final class StudioModel: ObservableObject {
    @Published var settings = BookSettings()
    @Published var project = ""
    @Published var repository = ""
    @Published var python = ""
    @Published var outputFolder = ""
    @Published var snapshot: BridgeResponse?
    @Published var busy = false
    @Published var prepared = false
    @Published var notice = "Select an EPUB to begin."
    @Published var error: String?
    @Published var showLogs = false
    @Published var showSetup = false
    @Published var previewing = false
    private var player: AVAudioPlayer?
    private var polling: Task<Void, Never>?
    private var generation = UUID()

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let fallback = home.appendingPathComponent("Work/ebooks-to-audiobook-conversion").path
        let bundleParent = Bundle.main.bundleURL.deletingLastPathComponent().path
        let detected = FileManager.default.fileExists(atPath: bundleParent + "/app_bridge.py") ? bundleParent : fallback
        repository = UserDefaults.standard.string(forKey: "repository") ?? detected
        python = UserDefaults.standard.string(forKey: "python") ?? home.appendingPathComponent("Work/Audiobooks/.kokoro-venv/bin/python").path
        outputFolder = UserDefaults.standard.string(forKey: "outputFolder") ?? home.appendingPathComponent("Work/Audiobooks").path
        settings.modelDir = UserDefaults.standard.string(forKey: "modelDir") ?? home.appendingPathComponent("Work/Audiobooks/kokoro-model").path
        settings.sensorDir = UserDefaults.standard.string(forKey: "sensorDir") ?? home.appendingPathComponent("Work/Audiobooks/tools/smctemp").path
        let last = UserDefaults.standard.string(forKey: "project") ?? home.appendingPathComponent("Work/Audiobooks/Emotional Design").path
        if FileManager.default.fileExists(atPath: last + "/book.json") {
            project = last
            Task { await loadProject() }
        }
        polling = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2))
                guard let self else { return }
                if self.prepared && !self.busy { await self.refresh() }
            }
        }
    }

    var active: Bool { snapshot?.active == true }
    var paused: Bool { snapshot?.paused == true }
    var complete: Bool { snapshot?.complete == true }
    var audioLocked: Bool { active || (snapshot?.progress?.saved ?? 0) > 0 }
    var legacyActive: Bool { active && snapshot?.legacy == true }
    var phase: String { busy ? "Working…" : (snapshot?.phase ?? "New audiobook") }
    var progressText: String { String(format: "%.1f%%", snapshot?.progress?.percent ?? 0) }
    var eta: String {
        guard active, let seconds = snapshot?.progress?.etaSeconds, seconds > 0 else { return "Learning the pace" }
        let minutes = Int(ceil(seconds / 60))
        return "About \(minutes) min remaining"
    }

    func persistPaths() {
        for (key, value) in [("repository", repository), ("python", python), ("outputFolder", outputFolder),
                             ("modelDir", settings.modelDir), ("sensorDir", settings.sensorDir)] {
            UserDefaults.standard.set(value, forKey: key)
        }
    }

    private func call(_ action: String, config: BookSettings? = nil) async throws -> BridgeResponse {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        let input = try encoder.encode(BridgeRequest(action: action, project: project, config: config))
        let executable = python, repo = repository
        let data = try await Task.detached(priority: .utility) {
            guard FileManager.default.isExecutableFile(atPath: executable) else {
                throw BridgeError.message("Select the Python runtime in Setup.")
            }
            guard FileManager.default.fileExists(atPath: repo + "/app_bridge.py") else {
                throw BridgeError.message("Select the conversion repository in Setup.")
            }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = [repo + "/app_bridge.py"]
            process.currentDirectoryURL = URL(fileURLWithPath: repo)
            var environment = ProcessInfo.processInfo.environment
            environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            environment["OMP_NUM_THREADS"] = "1"
            process.environment = environment
            let stdin = Pipe(), output = Pipe()
            process.standardInput = stdin; process.standardOutput = output; process.standardError = FileHandle.nullDevice
            try process.run()
            try stdin.fileHandleForWriting.write(contentsOf: input)
            try stdin.fileHandleForWriting.close()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard !data.isEmpty else { throw BridgeError.message("The conversion engine did not reply. Check the runtime in Setup.") }
            return data
        }.value
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(BridgeResponse.self, from: data)
        if !response.ok { throw BridgeError.message(response.error ?? "The operation failed.") }
        return response
    }

    func refresh() async {
        let token = generation
        do {
            let response = try await call("status")
            guard generation == token else { return }
            snapshot = response
        } catch { if generation == token { notice = "Status unavailable: \(error.localizedDescription)" } }
    }
    func loadProject() async {
        generation = UUID(); let token = generation
        busy = true
        defer { busy = false }
        do {
            let response = try await call("load")
            guard generation == token else { return }
            snapshot = response; settings = response.config ?? settings; prepared = true
            UserDefaults.standard.set(project, forKey: "project")
            notice = "Completed batches are saved automatically."
        } catch { self.error = error.localizedDescription; prepared = false }
    }
    func perform(_ action: String) {
        guard !busy else { return }
        generation = UUID()
        busy = true
        Task {
            defer { busy = false }
            do {
                persistPaths()
                if action == "prepare" {
                    let response = try await call("prepare", config: settings)
                    snapshot = response; settings = response.config ?? settings; prepared = true
                    UserDefaults.standard.set(project, forKey: "project")
                    snapshot = try await call("start")
                    notice = "Conversion started. You can close this window; the job continues."
                } else if action == "check" {
                    let response = try await call("check", config: settings)
                    notice = response.message ?? "Setup is ready."
                } else {
                    if action == "resume" { _ = try await call("save", config: settings) }
                    let response = try await call(action, config: action == "save" ? settings : nil)
                    snapshot = response
                    if action == "save" { settings = response.config ?? settings; notice = "Settings saved." }
                    if action == "pause" { notice = "Paused. Resume continues from saved batches." }
                    if action == "stop" { notice = "Stopping. Saved audio will be kept." }
                }
            } catch { self.error = error.localizedDescription }
        }
    }
    func newBook() {
        generation = UUID()
        let model = settings.modelDir, sensor = settings.sensorDir
        settings = BookSettings(); settings.modelDir = model; settings.sensorDir = sensor
        snapshot = nil; prepared = false; project = ""
        notice = "Select an EPUB and an output folder."
    }
    func chooseSource() {
        let panel = NSOpenPanel(); panel.title = "Select an EPUB file or unpacked EPUB folder"
        panel.canChooseFiles = true; panel.canChooseDirectories = true; panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            settings.source = url.path
            project = URL(fileURLWithPath: outputFolder).appendingPathComponent(url.deletingPathExtension().lastPathComponent).path
        }
    }
    func chooseExisting() {
        let panel = NSOpenPanel(); panel.title = "Open a conversion project"
        panel.canChooseFiles = false; panel.canChooseDirectories = true
        if panel.runModal() == .OK, let url = panel.url { project = url.path; Task { await loadProject() } }
    }
    func chooseFolder(_ field: String) {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = field == "python"
        panel.title = "Select \(field)"
        if panel.runModal() == .OK, let url = panel.url {
            switch field {
            case "repository": repository = url.path
            case "python": python = url.path
            case "model": settings.modelDir = url.path
            case "sensors": settings.sensorDir = url.path
            default:
                outputFolder = url.path
                if !settings.source.isEmpty { project = url.appendingPathComponent(URL(fileURLWithPath: settings.source).deletingPathExtension().lastPathComponent).path }
            }
            persistPaths()
        }
    }
    func reveal() {
        let path = complete ? (snapshot?.output ?? project) : project
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
    func openBooks() {
        guard complete, let path = snapshot?.output else { return }
        NSWorkspace.shared.open([URL(fileURLWithPath: path)], withApplicationAt: URL(fileURLWithPath: "/System/Applications/Books.app"), configuration: NSWorkspace.OpenConfiguration())
    }
    func previewVoice() {
        if previewing { player?.stop(); previewing = false; return }
        let name = ["af_heart": "Heart", "af_bella": "Bella", "am_michael": "Michael"][settings.voice] ?? "Heart"
        guard let url = Bundle.main.url(forResource: name, withExtension: "mp3", subdirectory: "Voice Samples") else {
            error = "The voice sample is not included in this app build."; return
        }
        do {
            player = try AVAudioPlayer(contentsOf: url); player?.play(); previewing = true
            let duration = player?.duration ?? 0
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(duration))
                if self?.player?.isPlaying == false { self?.previewing = false }
            }
        } catch { self.error = error.localizedDescription }
    }
}
