// swift-tools-version:5.5
import PackageDescription

let package = Package(
    name: "CteckaStitkySW",
    platforms: [.macOS(.v11)],
    targets: [
        .executableTarget(
            name: "CteckaStitkySW",
            path: "Sources/CteckaStitkySW",
            resources: [.copy("../../Scripts")]
        )
    ]
)
