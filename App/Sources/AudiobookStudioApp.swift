import SwiftUI
import AppKit

@MainActor
final class StudioAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Set the running Dock image too, even when Launch Services has an old placeholder cached.
        if let icon = StudioAssets.icon { NSApplication.shared.applicationIconImage = icon }
    }
}

@main
struct AudiobookStudioApp: App {
    @NSApplicationDelegateAdaptor(StudioAppDelegate.self) private var appDelegate
    @StateObject private var model = StudioModel()
    var body: some Scene {
        WindowGroup("Audiobook Studio") {
            StudioView(model: model)
                .frame(minWidth: 980, minHeight: 740)
                .tint(StudioPalette.accent)
                .groupBoxStyle(StudioCardStyle())
        }
        .defaultSize(width: 1100, height: 850)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Audiobook") { model.newBook() }.keyboardShortcut("n").disabled(model.busy)
                Button("Open Project…") { model.chooseExisting() }.keyboardShortcut("o").disabled(model.busy)
            }
            CommandGroup(replacing: .appSettings) {
                Button("Setup…") { model.showSetup = true }.keyboardShortcut(",")
            }
        }
    }
}

struct StudioView: View {
    @ObservedObject var model: StudioModel
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            HStack(alignment: .top, spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        bookControls
                        narrationControls
                        thermalControls
                        if model.prepared {
                            Button("Apply settings") { model.perform("save") }
                                .disabled(model.busy || model.legacyActive)
                            if model.legacyActive {
                                Text("This earlier conversion keeps its current settings. Stop and resume it in the app to apply new settings.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }.padding(24).disabled(model.busy)
                }.frame(minWidth: 500, idealWidth: 550)
                    .background(Color(nsColor: .windowBackgroundColor))
                Divider()
                ScrollView { progressPanel.padding(24) }
                    .frame(minWidth: 350, idealWidth: 400)
                    .background(Color(nsColor: .controlBackgroundColor).opacity(0.6))
            }
            Divider()
            HStack {
                if model.busy { ProgressView().controlSize(.small) }
                else { Image(systemName: "internaldrive").foregroundStyle(StudioPalette.accent) }
                Text(model.notice).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Spacer()
                Button("Setup…") { model.showSetup = true }.buttonStyle(.borderless)
            }.padding(.horizontal, 24).padding(.vertical, 12)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .task { await model.restoreProject() }
        .task(id: "\(scenePhase)-\(model.project)-\(model.shouldPoll)-\(model.busy)") {
            if scenePhase == .active && model.shouldPoll && !model.busy { await model.poll() }
        }
        .sheet(isPresented: $model.showSetup) { SetupView(model: model) }
        .sheet(isPresented: $model.showLogs) {
            VStack(alignment: .leading, spacing: 16) {
                HStack { Text("Conversion log").font(.title2.bold()); Spacer(); Button("Done") { model.showLogs = false } }
                ScrollView { Text(model.loadingLog ? "Loading log…" : model.logText).font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
            }.padding(24).frame(width: 800, height: 550)
        }
        .alert("Could not complete the action", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
            Button("Open Diagnostics") { model.openDiagnostics(); model.error = nil }
        } message: { Text(model.error ?? "") }
    }
    private var header: some View {
        HStack(spacing: 14) {
            StudioLogo()
            VStack(alignment: .leading, spacing: 3) {
                Text("Audiobook Studio").font(.system(.title2, design: .rounded, weight: .bold))
                Text(model.defaultNarration).font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            Button { model.newBook() } label: { Label("New Book", systemImage: "plus") }.disabled(model.busy)
            Button { model.chooseExisting() } label: { Label("Open Project…", systemImage: "folder") }.disabled(model.busy)
        }.padding(.horizontal, 24).padding(.vertical, 18)
    }
    private var bookControls: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text(model.settings.source.isEmpty ? "Choose an EPUB" : URL(fileURLWithPath: model.settings.source).lastPathComponent)
                        .lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                    if !model.prepared { Button("Choose…") { model.chooseSource() } }
                }
                if !model.prepared {
                    HStack { Text("Save in").foregroundStyle(.secondary); Text(URL(fileURLWithPath: model.outputFolder).lastPathComponent).lineLimit(1); Spacer(); Button("Choose…") { model.chooseFolder("output") } }
                    Text("A new project folder will be made for the book.").font(.caption).foregroundStyle(.secondary)
                }
                TextField("Title (read from the EPUB)", text: $model.settings.title).disabled(model.active)
                TextField("Author (read from the EPUB)", text: $model.settings.author).disabled(model.active)
                if model.prepared { TextField("Output file", text: $model.settings.outputName).disabled(model.active) }
            }.textFieldStyle(.roundedBorder).padding(8)
        } label: { Label("Book and output", systemImage: "book.closed") }
    }
    private var narrationControls: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                Text(model.narrationContext).font(.caption).foregroundStyle(.secondary)
                if model.audioLocked && model.settings.backend != "qwen" {
                    Button("New Qwen version of this book") { model.newQwenVersion() }
                        .disabled(model.settings.source.isEmpty)
                }
                Picker(model.audioLocked ? "Recorded engine" : "Engine", selection: Binding(get: { model.settings.backend }, set: { model.selectEngine($0) })) {
                    Text("Qwen3-TTS 1.7B · 6-bit (default)").tag("qwen")
                    Text("Voxtral 4B · 4-bit").tag("voxtral")
                    Text("Kokoro 82M · v1.0").tag("kokoro")
                }.disabled(model.audioLocked)
                HStack {
                    Picker("Voice", selection: $model.settings.voice) {
                        ForEach(model.voices, id: \.self) { Text(model.voiceLabel($0)).tag($0) }
                    }.disabled(model.audioLocked)
                    Button(model.previewing ? "Stop sample" : (model.settings.backend == "kokoro" ? "Listen" : "Make sample")) { model.previewVoice() }
                        .disabled(model.busy || (model.active && model.settings.backend != "kokoro"))
                }
                if model.settings.backend == "qwen" {
                    TextField("Narration style", text: $model.settings.instruct, axis: .vertical)
                        .lineLimit(2...4).textFieldStyle(.roundedBorder).disabled(model.audioLocked)
                    Text("English presets. Style instructions guide the voice.").font(.caption).foregroundStyle(.secondary)
                }
                if model.settings.backend == "voxtral" {
                    Text("20 preset voices. Language follows the voice prefix. Model license: CC-BY-NC-4.0.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    Text("Speed")
                    Slider(value: $model.settings.speed, in: 0.5...2, step: 0.05).disabled(model.audioLocked)
                    Text(model.settings.speed.formatted(.number.precision(.fractionLength(2))) + "×").monospacedDigit().frame(width: 48)
                }
                Picker("Audio quality", selection: $model.settings.bitrate) {
                    ForEach([64,96,128,192], id: \.self) { Text("\($0) kbps").tag($0) }
                }.disabled(model.audioLocked)
                if model.settings.backend != "kokoro" {
                    Text("Speed changes the generated audio and keeps its pitch.").font(.caption).foregroundStyle(.secondary)
                    DisclosureGroup("Chunk size and generation") {
                        VStack(alignment: .leading, spacing: 10) {
                            Stepper("Chunk limit: \(model.settings.chunkChars) characters", value: $model.settings.chunkChars, in: 500...1500, step: 100)
                            NumberRow(label: "Voice variation", value: $model.settings.temperature, unit: "", range: 0.1...1.5)
                            Stepper("Token limit: \(model.settings.maxTokens)", value: $model.settings.maxTokens, in: 512...8192, step: 512)
                            Text("Shorter chunks make retries smaller. Reaching the token limit stops the job instead of saving cut-off speech.").font(.caption).foregroundStyle(.secondary)
                        }.padding(.top,10).disabled(model.audioLocked)
                    }
                }
                DisclosureGroup("Silence and pacing") {
                    VStack(spacing: 10) {
                        NumberRow(label: "Between speech segments", value: $model.settings.paragraphGap, unit: "s", range: 0...3).disabled(model.audioLocked)
                        NumberRow(label: "At each chapter end", value: $model.settings.chapterGap, unit: "s", range: 0...10).disabled(model.audioLocked)
                        NumberRow(label: "Rest after each segment", value: $model.settings.segmentRest, unit: "s", range: 0...5).disabled(model.active)
                    }.padding(.top, 10)
                }
                if model.audioLocked {
                    Label("Saved audio keeps its original voice and pacing. A new version uses a separate folder.", systemImage: "lock")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.padding(8)
        } label: { Label("Narration", systemImage: "waveform") }
    }
    private var thermalControls: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                NumberRow(label: "CPU maximum target", value: $model.settings.ceilingC, unit: "°C", range: 50...90)
                NumberRow(label: "GPU maximum target", value: $model.settings.gpuCeilingC, unit: "°C", range: 50...93)
                DisclosureGroup("Pause and resume temperatures") {
                    VStack(spacing: 10) {
                        NumberRow(label: "CPU pause at", value: $model.settings.pauseC, unit: "°C", range: 42...88)
                        NumberRow(label: "CPU resume below", value: $model.settings.resumeC, unit: "°C", range: 40...87)
                        Divider()
                        NumberRow(label: "GPU pause at", value: $model.settings.gpuPauseC, unit: "°C", range: 42...91)
                        NumberRow(label: "GPU resume below", value: $model.settings.gpuResumeC, unit: "°C", range: 40...90)
                    }.padding(.top, 10)
                }
                DisclosureGroup("Cooling breaks") {
                    VStack(spacing: 10) {
                        NumberRow(label: "Work before a scheduled break", value: $model.settings.workSeconds, unit: "s", range: 1...600)
                        NumberRow(label: "Minimum break", value: $model.settings.restSeconds, unit: "s", range: 1...600)
                        NumberRow(label: "Cool readings before resume", value: $model.settings.stableSeconds, unit: "s", range: 0.5...30)
                    }.padding(.top, 10)
                }
                Text("Either sensor group can pause all workers. Both groups must cool before work resumes. Each pause must be at least 2°C below its target. Other apps can still raise the Mac’s temperature during a pause.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(8).disabled(model.legacyActive)
        } label: { Label("Temperature and cooling", systemImage: "thermometer.medium") }
    }
    private var progressPanel: some View {
        VStack(alignment: .leading, spacing: 22) {
            bookSummary
            HStack {
                Label(model.complete ? "Complete" : "Conversion", systemImage: model.complete ? "checkmark.circle.fill" : "waveform")
                    .font(.headline).foregroundStyle(StudioPalette.accent)
                Spacer()
                HStack(spacing: 6) {
                    Circle().fill(statusColor).frame(width: 6, height: 6)
                    Text(model.phase).font(.caption.weight(.medium)).lineLimit(2)
                }.padding(.horizontal, 10).padding(.vertical, 7)
                    .background(statusColor.opacity(0.09), in: RoundedRectangle(cornerRadius: 9))
            }
            VStack(alignment: .leading, spacing: 10) {
                Text("SAVED NARRATION").font(.system(size: 10, weight: .semibold)).tracking(1.5).foregroundStyle(.secondary)
                Text(model.progressText).font(.system(size: 56, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(StudioPalette.accent)
                ProgressView(value: model.snapshot?.progress?.percent ?? 0, total: 100)
                if let p = model.snapshot?.progress {
                    Text("\(p.saved.formatted()) of \(p.total.formatted()) words saved").font(.subheadline)
                    Text("\(Int(p.audioSeconds / 3600)) h \(Int(p.audioSeconds.truncatingRemainder(dividingBy: 3600) / 60)) min of audio saved")
                        .foregroundStyle(.secondary).font(.caption)
                    if model.active { Text(model.eta).foregroundStyle(.secondary).font(.caption) }
                }
            }
            HStack(spacing: 12) {
                TemperatureTile(name: "CPU", value: model.snapshot?.thermal?.cpuMaxC, target: model.snapshot?.thermal?.userTargetC ?? model.settings.ceilingC)
                TemperatureTile(name: "GPU", value: model.snapshot?.thermal?.gpuMaxC, target: model.snapshot?.thermal?.gpuTargetC ?? (model.legacyActive ? model.settings.ceilingC : model.settings.gpuCeilingC))
            }
            if let error = model.snapshot?.thermal?.error, !error.isEmpty {
                Label("Waiting for a valid temperature reading.", systemImage: "thermometer.medium.slash").font(.caption).foregroundStyle(.orange)
            }
            VStack(spacing: 10) {
                if model.complete {
                    Button { model.openBooks() } label: { Label("Open in Apple Books", systemImage: "book.fill").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).controlSize(.large)
                } else if !model.prepared {
                    Button { model.perform("prepare") } label: { Label("Prepare and Start", systemImage: "play.fill").frame(maxWidth: .infinity) }
                        .buttonStyle(.borderedProminent).controlSize(.large).disabled(model.settings.source.isEmpty || model.project.isEmpty || model.busy)
                } else {
                    HStack {
                        if model.active && !model.paused {
                            Button { model.perform("pause") } label: { Label("Pause", systemImage: "pause.fill").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent)
                        } else {
                            Button { model.perform("resume") } label: { Label("Resume", systemImage: "play.fill").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent)
                        }
                        Button { model.perform("stop") } label: { Label("Stop", systemImage: "stop.fill") }.buttonStyle(.bordered).disabled(!model.active && !model.paused)
                    }.controlSize(.large).disabled(model.busy)
                }
                if model.prepared {
                    HStack {
                        Button("Show Folder") { model.reveal() }
                        Button("View Log") { Task { await model.viewLog() } }
                        Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy)
                    }.buttonStyle(.borderless)
                }
            }
            Label("Two GPU workers · CPU inference off", systemImage: "lock.shield")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
            if let sections = model.snapshot?.progress?.sections {
                Divider()
                Text("Book sections").font(.headline)
                ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                    HStack(alignment: .top) {
                        Image(systemName: section.done == section.total ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(section.done == section.total ? Color.green : Color.secondary)
                        Text(section.title).font(.caption).lineLimit(2)
                        Spacer()
                        Text("\(Int(Double(section.done) / Double(max(section.total, 1)) * 100))%").font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }
                }
            } else {
                ContentUnavailableView("Ready for your next book", systemImage: "headphones", description: Text("Choose an EPUB. Audio, chapters, and progress stay in its project folder."))
            }
        }
    }
    private var statusColor: Color {
        if model.complete { return StudioPalette.accent }
        if model.paused || (model.active && model.snapshot?.thermal?.running == false) { return .orange }
        return model.active ? StudioPalette.accent : .secondary
    }
    private var bookSummary: some View {
        HStack(spacing: 16) {
            if let cover = model.coverImage {
                Image(nsImage: cover).resizable().scaledToFit().frame(width: 62, height: 84)
                    .clipShape(RoundedRectangle(cornerRadius: 5)).accessibilityHidden(true)
            } else {
                StudioLogo(size: 72)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(model.settings.title.isEmpty ? "Your next audiobook" : model.settings.title)
                    .font(.system(.title3, design: .serif, weight: .semibold)).lineLimit(3)
                if !model.settings.author.isEmpty { Text(model.settings.author).font(.subheadline).foregroundStyle(.secondary).lineLimit(2) }
                Text(model.voiceLabel(model.settings.voice) + " · " + model.settings.backend.capitalized)
                    .font(.caption).foregroundStyle(StudioPalette.accent)
            }
            Spacer(minLength: 0)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.bottom, 4)
    }
}

struct NumberRow: View {
    var label: String
    @Binding var value: Double
    var unit: String
    var range: ClosedRange<Double>
    var body: some View {
        HStack {
            Text(label).font(.subheadline)
            Spacer()
            TextField(label, value: $value, format: .number.precision(.fractionLength(0...2)))
                .labelsHidden().multilineTextAlignment(.trailing).textFieldStyle(.roundedBorder).frame(width: 65)
                .accessibilityLabel(label)
            Text(unit).foregroundStyle(.secondary).frame(width: 22, alignment: .leading)
            Stepper(label, value: $value, in: range, step: range.lowerBound < 1 ? 0.1 : 1).labelsHidden()
        }
    }
}
struct TemperatureTile: View {
    var name: String
    var value: Double?
    var target: Double
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(name, systemImage: name == "CPU" ? "cpu" : "square.stack.3d.up")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
            Text(value.map { String(format: "%.1f°C", $0) } ?? "—")
                .font(.title2.weight(.medium)).monospacedDigit()
                .foregroundStyle((value ?? 0) >= target ? Color.orange : Color.primary)
            Text("Target \(Int(target))°C").font(.caption2).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(.primary.opacity(0.06)))
    }
}

struct SetupView: View {
    @ObservedObject var model: StudioModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Local engine setup").font(.title2.bold())
            Button("Open local diagnostics") { model.openDiagnostics() }
            Text("Error reports stay on this Mac. No reports are sent to a server.").font(.caption).foregroundStyle(.secondary)
            Text("Kokoro uses the existing Python runtime. Qwen and Voxtral use a separate MLX runtime in this repository.").foregroundStyle(.secondary)
            pathRow("Repository", text: $model.repository, key: "repository")
            pathRow("Python runtime", text: $model.python, key: "python")
            pathRow("Kokoro model folder", text: $model.settings.modelDir, key: "model")
            pathRow("Temperature reader", text: $model.settings.sensorDir, key: "sensors")
            Label("GPU configuration is fixed: two Metal workers. CPU inference is off.", systemImage: "lock.fill").font(.caption)
            if model.settings.backend != "kokoro" {
                HStack {
                    Button("Install MLX Runtime") { model.perform("install") }.disabled(model.active)
                    Button("Download Selected Model") { model.perform("download") }.disabled(model.active)
                }
                Text("Models are stored in the repository’s models folder. Qwen uses about 2.7 GB; Voxtral uses about 2.5 GB. Download requires an internet connection.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(model.notice).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Check Setup") { model.perform("check") }.disabled(model.busy)
                if model.busy { ProgressView().controlSize(.small) }
                Spacer()
                Button("Done") { model.persistPaths(); dismiss() }.keyboardShortcut(.defaultAction)
            }
        }.padding(28).frame(width: 660).disabled(model.busy)
    }
    private func pathRow(_ label: String, text: Binding<String>, key: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption.weight(.medium))
            HStack { TextField(label, text: text).textFieldStyle(.roundedBorder); Button("Choose…") { model.chooseFolder(key) } }
        }.disabled(model.active && (key == "model" || key == "sensors"))
    }
}
