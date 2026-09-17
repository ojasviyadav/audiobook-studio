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
    var backend = "qwen"
    var voice = "Ryan"
    var speed = 1.25
    var instruct = "Natural audiobook narration. Calm, clear, steady pacing."
    var chunkChars = 1000
    var temperature = 0.8
    var maxTokens = 4096
    var bitrate = 96
    var paragraphGap = 0.2
    var chapterGap = 1.0
    var segmentRest = 0.5
    var ceilingC = 90.0
    var pauseC = 82.0
    var resumeC = 78.0
    var gpuCeilingC = 93.0
    var gpuPauseC = 89.0
    var gpuResumeC = 85.0
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
    var gpuTargetC: Double?
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
    var preview: String?
}
struct BridgeRequest: Encodable, Sendable {
    var action: String
    var project: String
    var config: BookSettings?
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
    @Published var diagnosticsID: String?
    @Published var coverImage: NSImage?
    @Published var logText = ""
    @Published var loadingLog = false
    private var player: AVAudioPlayer?
    private let bridge: BridgeOperation
    private let monitoring: any ErrorMonitoringService
    private var refreshing = false
    private var restored = false
    private var statusFailures = 0
    private var playbackTask: Task<Void, Never>?
    private var coverTask: Task<Void, Never>?
    private var generation = UUID()

    init(bridge: @escaping BridgeOperation = BridgeClient.call,
         monitoring: any ErrorMonitoringService = LocalErrorMonitoring.shared) {
        self.bridge = bridge
        self.monitoring = monitoring
        let home = FileManager.default.homeDirectoryForCurrentUser
        let fallback = home.appendingPathComponent("Work/ebooks-to-audiobook-conversion").path
        let bundleParent = Bundle.main.bundleURL.deletingLastPathComponent().path
        let detected = FileManager.default.fileExists(atPath: bundleParent + "/app_bridge.py") ? bundleParent : fallback
        repository = UserDefaults.standard.string(forKey: "repository") ?? detected
        let localPython = repository + "/.venv/bin/python"
        let legacyPython = home.appendingPathComponent("Work/Audiobooks/.kokoro-venv/bin/python").path
        let detectedPython = FileManager.default.isExecutableFile(atPath: localPython) ? localPython :
            (FileManager.default.isExecutableFile(atPath: legacyPython) ? legacyPython : "/usr/bin/python3")
        python = UserDefaults.standard.string(forKey: "python") ?? detectedPython
        outputFolder = UserDefaults.standard.string(forKey: "outputFolder") ?? home.appendingPathComponent("Work/Audiobooks").path
        settings.modelDir = UserDefaults.standard.string(forKey: "modelDir") ?? home.appendingPathComponent("Work/Audiobooks/kokoro-model").path
        let localSensors = repository + "/vendor/smctemp"
        settings.sensorDir = UserDefaults.standard.string(forKey: "sensorDir") ??
            (FileManager.default.isExecutableFile(atPath: localSensors + "/read_sensors") ? localSensors : home.appendingPathComponent("Work/Audiobooks/tools/smctemp").path)
        if let last = UserDefaults.standard.string(forKey: "project"), FileManager.default.fileExists(atPath: last + "/book.json") {
            project = last
        }
    }

    func restoreProject() async {
        guard !restored else { return }
        restored = true
        if !project.isEmpty { await loadProject() }
    }

    // SwiftUI owns this task. It cancels when the window becomes inactive or changes project.
    func poll() async {
        while !Task.isCancelled && prepared && !complete {
            do { try await Task.sleep(for: .seconds(statusFailures > 0 ? 15 : 2), tolerance: .milliseconds(250)) }
            catch { return }
            guard !Task.isCancelled else { return }
            if !busy { await refresh() }
        }
    }

    var shouldPoll: Bool { prepared && !complete }
    var defaultNarration: String { "New books: Qwen · Ryan · 1.25×" }
    var narrationContext: String {
        if audioLocked {
            return "Saved recording: \(voiceLabel(settings.voice)) · \(settings.backend.capitalized) · \(String(format: "%.2f", settings.speed))×. Changing the default does not change saved audio."
        }
        return "Settings for the next recording. Qwen is the default for new books."
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

    var voices: [String] {
        switch settings.backend {
        case "qwen": return ["Ryan", "Aiden"]
        case "voxtral": return ["casual_male", "casual_female", "cheerful_female", "neutral_male", "neutral_female", "fr_male", "fr_female", "es_male", "es_female", "de_male", "de_female", "it_male", "it_female", "pt_male", "pt_female", "nl_male", "nl_female", "ar_male", "hi_male", "hi_female"]
        default: return ["af_heart", "af_bella", "am_michael"]
        }
    }
    func voiceLabel(_ voice: String) -> String {
        ["af_heart":"Heart", "af_bella":"Bella", "am_michael":"Michael"][voice] ?? voice.replacingOccurrences(of: "_", with: " ").capitalized
    }
    func selectEngine(_ engine: String) {
        guard !busy && !audioLocked else { return }
        stopPlayback()
        settings.backend = engine
        settings.voice = engine == "qwen" ? "Ryan" : (engine == "voxtral" ? "neutral_male" : "af_heart")
        settings.speed = engine == "qwen" ? 1.25 : (engine == "kokoro" ? 0.95 : 1)
        settings.pauseC = engine == "kokoro" ? 86 : 82
        settings.resumeC = engine == "kokoro" ? 82 : 78
        settings.gpuPauseC = 89
        settings.gpuResumeC = 85
        settings.workSeconds = engine == "voxtral" ? 3 : 60
        settings.restSeconds = engine == "voxtral" ? 10 : 5
        settings.stableSeconds = 1
        settings.pauseC = min(settings.pauseC, settings.ceilingC - 2)
        settings.resumeC = min(settings.resumeC, settings.pauseC - 2)
        settings.gpuPauseC = min(settings.gpuPauseC, settings.gpuCeilingC - 2)
        settings.gpuResumeC = min(settings.gpuResumeC, settings.gpuPauseC - 2)
        notice = "Cooling defaults set for the selected engine. You can change them below."
        if !prepared && !settings.source.isEmpty { updateProjectPath() }
    }
    private func updateProjectPath() {
        let name = URL(fileURLWithPath: settings.source).deletingPathExtension().lastPathComponent
        project = URL(fileURLWithPath: outputFolder).appendingPathComponent(name + " — " + settings.backend).path
    }

    func persistPaths() {
        for (key, value) in [("repository", repository), ("python", python), ("outputFolder", outputFolder),
                             ("modelDir", settings.modelDir), ("sensorDir", settings.sensorDir)] {
            UserDefaults.standard.set(value, forKey: key)
        }
    }

    private func call(_ action: String, config: BookSettings? = nil) async throws -> BridgeResponse {
        // Capture every input before suspension. Never read paths from a later project.
        let request = BridgeRequest(action: action, project: project, config: config)
        let executable = python, repo = repository
        return try await bridge(request, executable, repo)
    }

    private func report(_ failure: Error, action: String, token: UUID, statusOnly: Bool = false) async {
        guard !(failure is CancellationError), generation == token, !Task.isCancelled else { return }
        let id = UUID().uuidString.prefix(8).uppercased()
        await monitoring.captureError(failure, context: ErrorContext(id: id, action: action, engine: settings.backend))
        guard generation == token, !Task.isCancelled else { return }
        diagnosticsID = id
        let message = UserFacingFailure.message(for: action) + " Report: " + id + "."
        if statusOnly { notice = message } else { error = message }
    }

    func refresh() async {
        guard prepared, !busy, !refreshing else { return }
        refreshing = true
        let token = generation
        defer { refreshing = false }
        do {
            let response = try await call("status")
            guard generation == token, !Task.isCancelled else { return }
            snapshot = response
            if statusFailures > 0 { notice = "Status updated." }
            statusFailures = 0
        } catch {
            guard generation == token, !(error is CancellationError), !Task.isCancelled else { return }
            statusFailures += 1
            if statusFailures == 1 { await report(error, action: "status", token: token, statusOnly: true) }
        }
    }

    func loadProject() async {
        guard !busy else { return }
        generation = UUID(); let token = generation
        stopPlayback(); coverTask?.cancel(); coverImage = nil
        snapshot = nil; prepared = false; logText = ""
        busy = true
        defer { if generation == token { busy = false } }
        do {
            let response = try await call("load")
            guard generation == token, !Task.isCancelled else { return }
            snapshot = response; settings = response.config ?? settings; prepared = true
            statusFailures = 0; error = nil; diagnosticsID = nil
            loadCover()
            UserDefaults.standard.set(project, forKey: "project")
            notice = audioLocked ? "Saved recording loaded. New books use Qwen, Ryan, at 1.25×." : "Project loaded."
        } catch {
            guard generation == token else { return }
            prepared = false
            await report(error, action: "load", token: token)
        }
    }

    func perform(_ action: String) {
        guard !busy else { return }
        generation = UUID(); let token = generation
        busy = true; error = nil
        Task { await execute(action, token: token) }
    }

    private func execute(_ action: String, token: UUID) async {
        defer { if generation == token { busy = false } }
        await monitoring.addBreadcrumb(Breadcrumb(action: action))
        do {
            persistPaths()
            if action == "prepare" {
                let response = try await call("prepare", config: settings)
                guard generation == token else { return }
                snapshot = response; settings = response.config ?? settings; prepared = true
                loadCover()
                UserDefaults.standard.set(project, forKey: "project")
                let started = try await call("start")
                guard generation == token else { return }
                snapshot = started
                notice = "Conversion started. You can close this window; the job continues."
            } else if ["check", "install", "download", "preview"].contains(action) {
                notice = ["install":"Installing the MLX runtime…", "download":"Downloading the selected model…", "preview":"Making a sample under temperature control…"][action] ?? "Checking setup…"
                let response = try await call(action, config: settings)
                guard generation == token else { return }
                notice = response.message ?? "Setup is ready."
                if let path = response.preview { try playSample(URL(fileURLWithPath: path)) }
            } else {
                if action == "resume" {
                    _ = try await call("save", config: settings)
                    guard generation == token else { return }
                }
                let response = try await call(action, config: action == "save" ? settings : nil)
                guard generation == token else { return }
                snapshot = response
                if action == "save" { settings = response.config ?? settings; notice = "Settings saved." }
                if action == "pause" { notice = "Paused. Resume continues from saved batches." }
                if action == "stop" { notice = "Stopping. Saved audio will be kept." }
            }
        } catch { await report(error, action: action, token: token) }
    }

    func newBook() {
        guard !busy else { return }
        generation = UUID(); stopPlayback(); coverTask?.cancel()
        let model = settings.modelDir, sensor = settings.sensorDir
        settings = BookSettings(); settings.modelDir = model; settings.sensorDir = sensor
        snapshot = nil; prepared = false; project = ""; coverImage = nil
        error = nil; diagnosticsID = nil; logText = ""; statusFailures = 0
        UserDefaults.standard.removeObject(forKey: "project")
        notice = "Qwen · Ryan · 1.25×. Select an EPUB and an output folder."
    }

    func newQwenVersion() {
        guard !busy, !settings.source.isEmpty else { return }
        let previous = settings
        newBook()
        settings.source = previous.source; settings.title = previous.title; settings.author = previous.author
        settings.cover = previous.cover
        // Each version gets its own output. Existing audio and receipts are never relabelled.
        updateProjectPath()
        project += " — " + String(UUID().uuidString.prefix(8))
        loadCover()
        notice = "New Qwen version at 1.25×. The saved recording is kept. Select Prepare and Start when ready."
    }

    private func loadCover() {
        coverTask?.cancel(); coverImage = nil
        guard let path = settings.cover else { return }
        let token = generation
        coverTask = Task { [weak self] in
            let data = await Task.detached(priority: .utility) { try? Data(contentsOf: URL(fileURLWithPath: path)) }.value
            guard !Task.isCancelled, let self, self.generation == token else { return }
            self.coverImage = data.flatMap(NSImage.init(data:))
        }
    }

    func viewLog() async {
        guard !loadingLog else { return }
        showLogs = true; loadingLog = true
        let token = generation
        defer { loadingLog = false }
        do {
            let response = try await call("logs")
            guard generation == token, !Task.isCancelled else { return }
            logText = response.log ?? "No log yet."
        } catch { await report(error, action: "logs", token: token) }
    }

    func openDiagnostics() { NSWorkspace.shared.open(LocalErrorMonitoring.directory) }

    func chooseSource() {
        guard !busy && !prepared else { return }
        let panel = NSOpenPanel(); panel.title = "Select an EPUB file or unpacked EPUB folder"
        panel.canChooseFiles = true; panel.canChooseDirectories = true; panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            settings.source = url.path
            updateProjectPath()
        }
    }
    func chooseExisting() {
        guard !busy else { return }
        let panel = NSOpenPanel(); panel.title = "Open a conversion project"
        panel.canChooseFiles = false; panel.canChooseDirectories = true
        if panel.runModal() == .OK, let url = panel.url { Task { await openProject(url.path) } }
    }
    func openProject(_ path: String) async {
        guard !busy else { return }
        project = path
        await loadProject()
    }

    func chooseFolder(_ field: String) {
        guard !busy else { return }
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
                if !prepared && !settings.source.isEmpty { updateProjectPath() }
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
        guard !busy else { return }
        if previewing { stopPlayback(); return }
        if settings.backend != "kokoro" { perform("preview"); return }
        let name = ["af_heart": "Heart", "af_bella": "Bella", "am_michael": "Michael"][settings.voice] ?? "Heart"
        guard let url = Bundle.main.url(forResource: name, withExtension: "mp3", subdirectory: "Voice Samples") else {
            error = "The voice sample is not included in this app build."; return
        }
        do { try playSample(url) } catch {
            let token = generation
            Task { await report(error, action: "preview", token: token) }
        }
    }
    private func stopPlayback() {
        playbackTask?.cancel(); player?.stop(); player = nil; previewing = false
    }

    private func playSample(_ url: URL) throws {
        stopPlayback()
        player = try AVAudioPlayer(contentsOf: url)
        guard player?.play() == true else { throw BridgeError.message("Audio playback failed.") }
        previewing = true
        let duration = player?.duration ?? 0
        playbackTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(duration)) } catch { return }
            guard !Task.isCancelled else { return }
            self?.previewing = false
        }
    }
}
