from update_locos import load_json, export_to_csv, create_summary, export_to_excel, LOCOS_FILE


def main():
    print("=" * 60)
    print("📊 LOCO EXPORTER")
    print("=" * 60)

    locos = load_json(LOCOS_FILE, {})
    if not locos:
        print(f"❌ {LOCOS_FILE} not found or empty")
        return

    print(f"\n📊 Loaded {len(locos)} stored locos")
    export_to_csv(locos)
    create_summary(locos)
    export_to_excel(locos)

    print("\n📁 Files updated:")
    print("   - loco_export.csv")
    print("   - loco_summary.txt")
    print("   - static/downloads/loco_database.xlsx")
    print("   - locos.json (database)")


if __name__ == "__main__":
    main()
