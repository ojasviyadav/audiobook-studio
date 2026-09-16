#!/usr/bin/env swift
import AppKit
import CoreGraphics

// Reproducible artwork. No external fonts or image assets are required.
let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let resources = root.appendingPathComponent("App/Resources")
let variants = resources.appendingPathComponent("IconVariants")
try FileManager.default.createDirectory(at: variants, withIntermediateDirectories: true)
func color(_ hex: UInt32, alpha: CGFloat = 1) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255,
            blue: CGFloat(hex & 255)/255, alpha: alpha)
}
func icon(_ top: UInt32, _ bottom: UInt32, _ accent: UInt32) -> CGImage {
    let c = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8, bytesPerRow: 0,
                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    let tile = CGPath(roundedRect: CGRect(x: 56, y: 56, width: 912, height: 912), cornerWidth: 206, cornerHeight: 206, transform: nil)
    c.saveGState()
    c.setShadow(offset: CGSize(width: 0, height: -12), blur: 24, color: color(0x071B1C, alpha: 0.22))
    c.addPath(tile); c.setFillColor(color(bottom)); c.fillPath()
    c.restoreGState()
    c.saveGState(); c.addPath(tile); c.clip()
    let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: [color(bottom), color(top)] as CFArray, locations: [0,1])!
    c.drawLinearGradient(gradient, start: CGPoint(x: 512, y: 56), end: CGPoint(x: 360, y: 968), options: [])
    c.restoreGState()
    // Two open pages share a strong central fold. The silhouette survives at 16 px.
    let left = CGMutablePath()
    left.move(to: CGPoint(x: 215,y: 335))
    left.addCurve(to: CGPoint(x: 491,y: 275), control1: CGPoint(x: 325,y: 355), control2: CGPoint(x: 424,y: 309))
    left.addLine(to: CGPoint(x: 491,y: 578))
    left.addCurve(to: CGPoint(x: 215,y: 630), control1: CGPoint(x: 401,y: 623), control2: CGPoint(x: 311,y: 650))
    left.closeSubpath()
    let right = CGMutablePath()
    right.move(to: CGPoint(x: 533,y: 275))
    right.addCurve(to: CGPoint(x: 809,y: 335), control1: CGPoint(x: 600,y: 309), control2: CGPoint(x: 699,y: 355))
    right.addLine(to: CGPoint(x: 809,y: 630))
    right.addCurve(to: CGPoint(x: 533,y: 578), control1: CGPoint(x: 713,y: 650), control2: CGPoint(x: 623,y: 623))
    right.closeSubpath()
    c.saveGState(); c.setShadow(offset: CGSize(width: 0, height: -9), blur: 12, color: color(0x031C1D, alpha: 0.25))
    c.addPath(left); c.setFillColor(color(0xFFF5DF)); c.fillPath()
    c.addPath(right); c.setFillColor(color(0xEBDDBE)); c.fillPath(); c.restoreGState()
    // Sound rises above the book. Rounded, solid bars remain clear at Dock sizes.
    let heights: [CGFloat] = [56, 104, 164, 104, 56]
    for (i,h) in heights.enumerated() {
        c.addPath(CGPath(roundedRect: CGRect(x: 366 + CGFloat(i)*62, y: 732-h/2, width: 44, height: h), cornerWidth: 22, cornerHeight: 22, transform: nil))
        c.setFillColor(color(accent)); c.fillPath()
    }
    return c.makeImage()!
}
func save(_ image: CGImage, to url: URL) throws {
    let rep = NSBitmapImageRep(cgImage: image)
    try rep.representation(using: .png, properties: [:])!.write(to: url)
}
let palettes: [(String,UInt32,UInt32,UInt32)] = [
    ("Teal",0x287B78,0x103A40,0xF4C979),
    ("Indigo",0x575781,0x262C4C,0xF4C979),
    ("Ember",0xAF684C,0x593934,0xFFDCA3)
]
for (name,top,bottom,accent) in palettes {
    try save(icon(top,bottom,accent),to: variants.appendingPathComponent(name+".png"))
}
let master = icon(palettes[0].1,palettes[0].2,palettes[0].3)
try save(master,to: resources.appendingPathComponent("AppIcon.png"))
let iconset = resources.appendingPathComponent("AppIcon.iconset")
try FileManager.default.createDirectory(at: iconset,withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let pixels = size*scale
        let c = CGContext(data:nil,width:pixels,height:pixels,bitsPerComponent:8,bytesPerRow:0,
                          space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
        c.interpolationQuality = .high
        c.draw(master,in:CGRect(x:0,y:0,width:pixels,height:pixels))
        try save(c.makeImage()!,to:iconset.appendingPathComponent("icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"))
    }
}
let process = Process()
process.executableURL = URL(fileURLWithPath:"/usr/bin/iconutil")
process.arguments = ["-c","icns",iconset.path,"-o",resources.appendingPathComponent("AppIcon.icns").path]
try process.run(); process.waitUntilExit()
guard process.terminationStatus == 0 else { fatalError("Icon conversion failed") }
print("Generated three palettes. Installed Teal as the app icon.")
