import zipfile, os, shutil
project_dir = r'C:\Users\admin\.gemini\antigravity\scratch\pokemon_ai_battle'
output_name = 'submission_v68.zip'
output_path = os.path.join(project_dir, output_name)

with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    zipf.write(os.path.join(project_dir, 'v68_agent', 'main.py'), 'main.py')
    print("Added: main.py")
    cg_dir = os.path.join(project_dir, 'cg')
    for root, dirs, files in os.walk(cg_dir):
        for file in files:
            fp = os.path.join(root, file)
            arcname = os.path.relpath(fp, project_dir)
            zipf.write(fp, arcname)
            print(f"Added: {arcname}")

print(f"\nZip created: {output_path}")
shutil.copy2(output_path, r'C:\Users\admin\Downloads\submission_v68.zip')
print("Copied to Downloads")
