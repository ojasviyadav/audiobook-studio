import SwiftUI
import AppKit

// System surfaces retain contrast in both light and dark appearances.
enum StudioPalette {
    static let accent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(red: 0.43, green: 0.78, blue: 0.73, alpha: 1)
            : NSColor(red: 0.09, green: 0.38, blue: 0.38, alpha: 1)
    })
}

struct StudioCardStyle: GroupBoxStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            configuration.label.font(.headline).foregroundStyle(StudioPalette.accent)
            configuration.content.frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(.primary.opacity(0.06)))
    }
}

@MainActor
enum StudioAssets {
    static let icon: NSImage? = Bundle.main.url(forResource: "AppIcon", withExtension: "png")
        .flatMap { NSImage(contentsOf: $0) }
}

struct StudioLogo: View {
    var size: CGFloat = 52
    var body: some View {
        Group {
            if let icon = StudioAssets.icon {
                Image(nsImage: icon).resizable().interpolation(.high).scaledToFit()
            } else {
                Image(systemName: "book.closed.fill").resizable().scaledToFit()
                    .padding(10).foregroundStyle(StudioPalette.accent)
            }
        }.frame(width: size, height: size).accessibilityHidden(true)
    }
}
