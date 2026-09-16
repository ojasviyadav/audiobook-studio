import SwiftUI
import AppKit

@main
struct AudiobookStudioApp: App {
    @StateObject private var model = StudioModel()
    var body: some Scene {
        WindowGroup("Audiobook Studio") {
            StudioView(model: model)
                .frame(minWidth: 950, minHeight: 760)
                .tint(.indigo)
        }
        .defaultSize(width: 1050, height: 850)
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
                }.frame(minWidth: 470, idealWidth: 510)
                Divider()
                ScrollView { progressPanel.padding(24) }
                    .frame(minWidth: 350, idealWidth: 400)
                    .background(Color(nsColor: .controlBackgroundColor).opacity(0.6))
            }
            Divider()
            HStack {
                Image(systemName: "internaldrive").foregroundStyle(.secondary)
                Text(model.notice).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Spacer()
                Button("Setup…") { model.showSetup = true }.buttonStyle(.borderless)
            }.padding(.horizontal, 24).padding(.vertical, 12)
        }
        .sheet(isPresented: $model.showSetup) { SetupView(model: model) }
        .sheet(isPresented: $model.showLogs) {
            VStack(alignment: .leading, spacing: 16) {
                HStack { Text("Conversion log").font(.title2.bold()); Spacer(); Button("Done") { model.showLogs = false } }
                ScrollView { Text(model.snapshot?.log ?? "No log yet.").font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
            }.padding(24).frame(width: 800, height: 550)
        }
        .alert("Could not complete the action", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
    }
    private var header: some View {
        HStack(spacing: 14) {
            Image(systemName: "book.and.wrench.fill").font(.system(size: 30)).foregroundStyle(.indigo)
            VStack(alignment: .leading, spacing: 3) {
                Text("Audiobook Studio").font(.title2.bold())
                Text("Your books, read aloud on your Mac").font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            Label("2 GPU workers · Fixed", systemImage: "lock.fill")
                .font(.caption.weight(.medium)).padding(9)
                .background(.indigo.opacity(0.09), in: Capsule())
            Button("New Book") { model.newBook() }.disabled(model.busy)
            Button("Open Project…") { model.chooseExisting() }.disabled(model.busy)
        }.padding(24)
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
                HStack {
                    Picker("Voice", selection: $model.settings.voice) {
                        Text("Heart · American English").tag("af_heart")
                        Text("Bella · American English").tag("af_bella")
                        Text("Michael · American English").tag("am_michael")
                    }.disabled(model.audioLocked)
                    Button(model.previewing ? "Stop sample" : "Listen") { model.previewVoice() }
                }
                HStack {
                    Text("Speed")
                    Slider(value: $model.settings.speed, in: 0.5...2, step: 0.05).disabled(model.audioLocked)
                    Text(model.settings.speed.formatted(.number.precision(.fractionLength(2))) + "×").monospacedDigit().frame(width: 48)
                }
                Picker("Audio quality", selection: $model.settings.bitrate) {
                    ForEach([64,96,128,192], id: \.self) { Text("\($0) kbps").tag($0) }
                }.disabled(model.audioLocked)
                DisclosureGroup("Silence and pacing") {
                    VStack(spacing: 10) {
                        NumberRow(label: "Between speech segments", value: $model.settings.paragraphGap, unit: "s", range: 0...3).disabled(model.audioLocked)
                        NumberRow(label: "At each chapter end", value: $model.settings.chapterGap, unit: "s", range: 0...10).disabled(model.audioLocked)
                        NumberRow(label: "Rest after each segment", value: $model.settings.segmentRest, unit: "s", range: 0...5).disabled(model.active)
                    }.padding(.top, 10)
                }
                if model.audioLocked {
                    Label("Saved audio locks voice and pacing. Use New Book to change them.", systemImage: "lock")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.padding(8)
        } label: { Label("Narration · Kokoro", systemImage: "waveform") }
    }
    private var thermalControls: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                NumberRow(label: "Maximum target", value: $model.settings.ceilingC, unit: "°C", range: 50...90)
                NumberRow(label: "Pause at", value: $model.settings.pauseC, unit: "°C", range: 42...88)
                NumberRow(label: "Resume below", value: $model.settings.resumeC, unit: "°C", range: 40...87)
                DisclosureGroup("Cooling breaks") {
                    VStack(spacing: 10) {
                        NumberRow(label: "Work before a scheduled break", value: $model.settings.workSeconds, unit: "s", range: 1...600)
                        NumberRow(label: "Minimum break", value: $model.settings.restSeconds, unit: "s", range: 1...600)
                        NumberRow(label: "Cool readings before resume", value: $model.settings.stableSeconds, unit: "s", range: 0.5...30)
                    }.padding(.top, 10)
                }
                Text("Pause must be at least 2°C below the target. Other apps can still raise the Mac’s temperature during a pause.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(8).disabled(model.legacyActive)
        } label: { Label("Temperature and cooling", systemImage: "thermometer.medium") }
    }
    private var progressPanel: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack {
                Text("Conversion").font(.title3.bold()); Spacer()
                Circle().fill(model.active ? Color.green : Color.secondary).frame(width: 8, height: 8)
                Text(model.phase).font(.caption).lineLimit(2)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text(model.progressText).font(.system(size: 48, weight: .semibold, design: .rounded)).monospacedDigit()
                ProgressView(value: model.snapshot?.progress?.percent ?? 0, total: 100)
                if let p = model.snapshot?.progress {
                    Text("\(p.saved.formatted()) of \(p.total.formatted()) words saved").font(.subheadline)
                    Text("\(Int(p.audioSeconds / 3600)) h \(Int(p.audioSeconds.truncatingRemainder(dividingBy: 3600) / 60)) min of audio saved")
                        .foregroundStyle(.secondary).font(.caption)
                    if model.active { Text(model.eta).foregroundStyle(.secondary).font(.caption) }
                }
            }
            HStack(spacing: 12) {
                TemperatureTile(name: "CPU", value: model.snapshot?.thermal?.cpuMaxC, target: model.settings.ceilingC)
                TemperatureTile(name: "GPU", value: model.snapshot?.thermal?.gpuMaxC, target: model.settings.ceilingC)
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
                            Button { model.perform("pause") } label: { Label("Pause", systemImage: "pause.fill").frame(maxWidth: .infinity) }
                        } else {
                            Button { model.perform("resume") } label: { Label("Resume", systemImage: "play.fill").frame(maxWidth: .infinity) }
                        }
                        Button { model.perform("stop") } label: { Label("Stop", systemImage: "stop.fill") }.disabled(!model.active && !model.paused)
                    }.buttonStyle(.borderedProminent).controlSize(.large).disabled(model.busy)
                }
                if model.prepared {
                    HStack {
                        Button("Show Folder") { model.reveal() }
                        Button("View Log") { model.showLogs = true }
                    }.buttonStyle(.borderless)
                }
            }
            Label("Two GPU workers · CPU inference off", systemImage: "lock.shield")
                .font(.caption.weight(.medium)).foregroundStyle(.indigo)
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
            Text(name).font(.caption).foregroundStyle(.secondary)
            Text(value.map { String(format: "%.1f°C", $0) } ?? "—")
                .font(.title2.weight(.medium)).monospacedDigit()
                .foregroundStyle((value ?? 0) >= target ? Color.orange : Color.primary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct SetupView: View {
    @ObservedObject var model: StudioModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Local engine setup").font(.title2.bold())
            Text("The app uses the Kokoro runtime and model already on this Mac. These paths are saved for the next launch.").foregroundStyle(.secondary)
            pathRow("Repository", text: $model.repository, key: "repository")
            pathRow("Python runtime", text: $model.python, key: "python")
            pathRow("Model folder", text: $model.settings.modelDir, key: "model")
            pathRow("Temperature reader", text: $model.settings.sensorDir, key: "sensors")
            Label("GPU configuration is fixed: two Metal workers, two host threads each.", systemImage: "lock.fill").font(.caption)
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
