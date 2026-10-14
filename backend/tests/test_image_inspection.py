from pathlib import Path

from app.services.image_inspection import ImageInspectionService


def main():
    project_root = Path(__file__).resolve().parents[2]

    # Place a test image at this path.
    image_path = project_root / "data" / "sample_images" / "factory.jpg"

    if not image_path.exists():
        raise FileNotFoundError(
            f"Test image not found: {image_path}\n"
            "Place a factory inspection image at this location first."
        )

    inspector = ImageInspectionService()

    result = inspector.inspect_image(
        image_path=image_path,
        machine_id="MACHINE-001",
    )

    print("\nFACTORY IMAGE INSPECTION")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()