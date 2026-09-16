// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "AudiobookStudio",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "AudiobookStudio", targets: ["AudiobookStudio"])],
    targets: [
        .executableTarget(name: "AudiobookStudio", path: "App/Sources"),
        .testTarget(name: "StudioTests", dependencies: ["AudiobookStudio"], path: "App/Tests")
    ]
)
