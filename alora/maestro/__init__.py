from os.path import abspath, dirname, join
import json

module_dir = dirname(abspath(__file__))
settings_path = join(module_dir, "MaestroCore","settings.txt")

def get_settings():
    with open(settings_path, "r") as settingsFile:
        settings = json.load(settingsFile)
    return settings
