import SwiftUI
import Metal

struct NarratorOption: Identifiable, Sendable {
    let id: String
    let name: String
    let qualityOrder: Int
    let qualityNote: String
    let compute: String
    let weights: String
    let deviceNote: String
    let timing: String
    let source: URL

    var shortName: String { id == "qwen" ? "Qwen" : id.capitalized }
    var purpose: String {
        switch id {
        case "qwen": return "Quality first"
        case "voxtral": return "More voice choices"
        default: return "Less processing"
        }
    }

    static let all: [NarratorOption] = [
        .init(id: "qwen", name: "Qwen3-TTS 1.7B CustomVoice · 6-bit", qualityOrder: 1,
              qualityNote: "First choice for expressive narration. Supports style instructions. Ryan is the default.",
              compute: "Higher load", weights: "About 2.7 GB",
              deviceNote: "Choose for voice quality when longer processing time is acceptable.",
              timing: "Local sample: 302 s for 669 words. About 2.6× the Kokoro time, with different cooling settings.",
              source: URL(string: "https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit")!),
        .init(id: "voxtral", name: "Voxtral 4B TTS · 4-bit", qualityOrder: 2,
              qualityNote: "Second voice to try. Offers 20 presets, including five English voices.",
              compute: "Higher load", weights: "About 2.5 GB",
              deviceNote: "Try a sample to check voice and cooling needs. The app uses frequent cooling breaks.",
              timing: "Speed rank unknown. The local test had interruptions and changed cooling settings. Published speed is not a result from this Mac.",
              source: URL(string: "https://huggingface.co/mlx-community/Voxtral-4B-TTS-2603-mlx-4bit")!),
        .init(id: "kokoro", name: "Kokoro 82M · v1.0", qualityOrder: 3,
              qualityNote: "Third voice to try when quality comes first. A useful choice for fast, simple narration.",
              compute: "Lowest load", weights: "About 0.33 GB",
              deviceNote: "Start here when memory, processing time, or cooling capacity is limited.",
              timing: "Local sample: 115 s for 669 words. Faster than Qwen in this test. Heart, Bella, and Michael are available.",
              source: URL(string: "https://huggingface.co/hexgrad/Kokoro-82M")!)
    ]
}

struct NarrationDevice: Sendable {
    let gpu: String?
    let memoryGB: Int
    let appleSilicon: Bool

    static let current: NarrationDevice = {
        #if arch(arm64)
        let appleSilicon = true
        #else
        let appleSilicon = false
        #endif
        return NarrationDevice(gpu: MTLCreateSystemDefaultDevice()?.name,
                               memoryGB: Int(ProcessInfo.processInfo.physicalMemory / 1_073_741_824),
                               appleSilicon: appleSilicon)
    }()

    var summary: String { "\(gpu ?? "No Metal GPU detected") · \(memoryGB) GB memory" }
    var guidance: String {
        guard appleSilicon, gpu != nil else {
            return "This app’s fixed GPU setup requires Apple Silicon and Metal. No CPU fallback is offered."
        }
        if gpu?.contains("M4 Pro") == true && memoryGB == 48 {
            return "All three models completed samples on an M4 Pro with 48 GB. Qwen is the quality default; Kokoro is the lighter option."
        }
        return "No local timing comparison is available for this device. Start with a short sample. Kokoro has the smallest model; Qwen is the quality default."
    }
}

struct ModelGuideView: View {
    @ObservedObject var model: StudioModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Choose a narration model").font(.title2.bold())
                    Text("Voice quality, processing needs, and your Mac").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label(NarrationDevice.current.summary, systemImage: "desktopcomputer").font(.headline)
                        Text(NarrationDevice.current.guidance)
                        Text("Two GPU workers are fixed. Each loads its own model. Model file size is not total memory use; audio buffers, the runtime, and other apps need more memory.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                        .background(StudioPalette.accent.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))

                    HStack(alignment: .top, spacing: 12) {
                        ForEach(NarratorOption.all) { option in
                            modelCard(option)
                        }
                    }

                    Text("Quality order is a listening suggestion, not a measured score. Qwen is the current preference; the order of Voxtral and Kokoro is provisional. Listen before choosing.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("Processing: Kokoro is the lightest option. Qwen and Voxtral need more resources; their relative speed and power use are not established. A smaller download does not mean a faster model.")
                        .font(.caption).foregroundStyle(.secondary)

                    DisclosureGroup("Timing evidence and model details") {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(NarratorOption.all) { option in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(option.name).font(.subheadline.bold())
                                    Text(option.timing).font(.caption)
                                    Link("Model details and license", destination: option.source).font(.caption)
                                }
                            }
                            Text("Local timing: two GPU workers on M4 Pro / 48 GB, 669 source words; Qwen at 1.0× and Kokoro at 0.95×. Cooling and setup differed. The current Qwen default is 1.25×; this changes audio speed after generation and does not imply 25% faster processing.")
                                .font(.caption).foregroundStyle(.secondary)
                        }.padding(.top, 10)
                    }
                    if model.audioLocked {
                        Label("This recording keeps its original model. Use New Book to choose another model.", systemImage: "lock")
                            .font(.caption)
                    } else {
                        Text("Select a model, then use Make sample or Listen in Narration before starting a book.").font(.caption)
                    }
                }.padding(.trailing, 6)
            }
        }.padding(24).frame(width: 900, height: 780)
            .background(Color(nsColor: .windowBackgroundColor))
    }

    private func modelCard(_ option: NarratorOption) -> some View {
        let selected = model.settings.backend == option.id
        return VStack(alignment: .leading, spacing: 12) {
            Label(option.purpose, systemImage: option.id == "kokoro" ? "bolt" : (option.id == "qwen" ? "headphones" : "person.wave.2"))
                .font(.caption.bold()).foregroundStyle(StudioPalette.accent)
            Text(option.shortName).font(.title2.bold())
            Text(option.id == "qwen" ? "1.7B CustomVoice · 6-bit" : (option.id == "voxtral" ? "4B TTS · 4-bit" : "82M · v1.0"))
                .font(.caption).foregroundStyle(.secondary)
            Divider()
            HStack { Text("Quality choice"); Spacer(); Text("#\(option.qualityOrder)").bold() }.font(.subheadline)
            HStack { Text("Processing"); Spacer(); Text(option.compute).bold() }.font(.subheadline)
            HStack { Text("Model files"); Spacer(); Text(option.weights) }.font(.caption).foregroundStyle(.secondary)
            Text(option.qualityNote).font(.callout).frame(minHeight: 60, alignment: .top)
            Text(option.deviceNote).font(.caption).foregroundStyle(.secondary).frame(minHeight: 54, alignment: .top)
            if selected {
                Label(model.audioLocked ? "Recorded model" : "Selected", systemImage: "checkmark.circle.fill")
                    .font(.subheadline.weight(.medium)).foregroundStyle(StudioPalette.accent)
                    .frame(maxWidth: .infinity).padding(.vertical, 4)
            } else {
                Button {
                    model.selectEngine(option.id)
                    dismiss()
                } label: {
                    Label("Use \(option.shortName)", systemImage: "arrow.right.circle")
                        .frame(maxWidth: .infinity)
                }.buttonStyle(.bordered).disabled(model.busy || model.audioLocked)
            }
            Text(option.id == "voxtral" ? "CC-BY-NC-4.0 · Noncommercial" : "Apache-2.0")
                .font(.caption2).foregroundStyle(.secondary)
        }.padding(16).frame(maxWidth: .infinity, alignment: .topLeading)
            .background(selected ? StudioPalette.accent.opacity(0.07) : Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(selected ? StudioPalette.accent : .primary.opacity(0.08), lineWidth: selected ? 1.5 : 1))
    }
}
