#!/usr/bin/env python3
"""Telecharge les donnees GTFS statiques STM une fois par semaine"""

import sys
import json
import zipfile
import shutil
import requests
import os
from datetime import datetime
from pathlib import Path


class GTFSDownloader:
    """Gestionnaire de telechargement GTFS STM."""

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.data_dir = self.project_root / "data" / "gtfs"
        self.archive_dir = self.data_dir / "archives"
        self.current_dir = self.data_dir / "gtfs_stm"
        self.manifest_file = self.data_dir / "gtfs_manifest.json"
        self.log_file = self.data_dir / "fetch_gtfs.log"

        sys.path.insert(0, str(self.project_root / "Skills"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        print(log_msg)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    def get_gtfs_url(self):
        return "https://www.stm.info/sites/default/files/gtfs/gtfs_stm.zip"

    def download_gtfs(self):
        self.log("Demarrage du telechargement GTFS...")
        url = self.get_gtfs_url()
        temp_zip = self.data_dir / f"gtfs_stm_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        try:
            self.log(f"Telechargement depuis {url}")
            response = requests.get(url, timeout=120)
            response.raise_for_status()

            with open(temp_zip, 'wb') as f:
                f.write(response.content)

            file_size_mb = temp_zip.stat().st_size / (1024 * 1024)
            self.log(f"Telechargement reussi ({file_size_mb:.1f} MB)")
            return str(temp_zip)

        except Exception as e:
            self.log(f"Erreur telechargement: {e}", "ERROR")
            raise

    def archive_old_version(self):
        if not self.current_dir.exists():
            self.log("Aucune version anterieure a archiver")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"gtfs_stm_{timestamp}"
        archive_path = self.archive_dir / archive_name

        try:
            self.log("Archivage de la version actuelle...")
            shutil.make_archive(str(archive_path), 'zip', self.current_dir)
            self.log(f"Version archivee: {archive_name}.zip")
            shutil.rmtree(self.current_dir)
            self.log("Ancien repertoire supprime")
        except Exception as e:
            self.log(f"Erreur archivage: {e}", "ERROR")
            raise

    def extract_gtfs(self, zip_path):
        try:
            self.log("Extraction du fichier GTFS...")
            with zipfile.ZipFile(zip_path, 'r') as z:
                required_files = ['stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt']
                namelist = z.namelist()
                missing = [f for f in required_files if f not in namelist]
                if missing:
                    raise ValueError(f"Fichiers GTFS manquants: {missing}")
                self.current_dir.mkdir(parents=True, exist_ok=True)
                z.extractall(self.current_dir)
            self.log("Extraction reussie")
        except Exception as e:
            self.log(f"Erreur extraction: {e}", "ERROR")
            raise

    def cleanup_old_archives(self, keep_count=4):
        try:
            archives = sorted(self.archive_dir.glob("gtfs_stm_*.zip"), reverse=True)
            if len(archives) > keep_count:
                to_delete = archives[keep_count:]
                self.log(f"Nettoyage: {len(to_delete)} archive(s) supprimee(s)")
                for archive in to_delete:
                    archive.unlink()
        except Exception as e:
            self.log(f"Erreur cleanup: {e}", "WARNING")

    def update_manifest(self, zip_path):
        try:
            import hashlib
            with open(zip_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            manifest = {
                "last_update": datetime.now().isoformat(),
                "gtfs_sha256": file_hash,
                "file_size_mb": Path(zip_path).stat().st_size / (1024 * 1024),
                "location": str(self.current_dir),
                "version": "stm_gtfs_2026"
            }
            with open(self.manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            self.log("Manifeste mise a jour")
        except Exception as e:
            self.log(f"Erreur manifeste: {e}", "WARNING")

    def run(self):
        temp_zip = None
        try:
            self.log("=" * 80)
            self.log("DEBUT: Mise a jour GTFS STM")
            self.log("=" * 80)

            temp_zip = self.download_gtfs()
            self.archive_old_version()
            self.extract_gtfs(temp_zip)
            self.update_manifest(temp_zip)
            self.cleanup_old_archives(keep_count=4)

            self.log("=" * 80)
            self.log("SUCCES: Donnees GTFS mises a jour")
            self.log("=" * 80)
            return True

        except Exception as e:
            self.log(f"ERREUR: {e}", "ERROR")
            self.log("=" * 80)
            return False

        finally:
            if temp_zip and Path(temp_zip).exists():
                try:
                    Path(temp_zip).unlink()
                    self.log("Fichier temporaire supprime")
                except Exception as e:
                    self.log(f"Impossible de supprimer fichier temp: {e}", "WARNING")


def main():
    downloader = GTFSDownloader()
    success = downloader.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
