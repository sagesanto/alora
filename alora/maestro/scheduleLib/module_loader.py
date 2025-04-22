# Sage Santomenna 2025
# keep track of Maestro modules and provide an interface for loading them

# first, go through and find all the modules. add any to the registry that aren't already there
# then, provide a function to load a module by name, one that loads only activated modules, and one that loads all modules
# provide a function to activate/deactivate a module by name

import sys, os
from os.path import abspath, dirname, join, pardir, basename
import sqlite3
import glob
import tomlkit
from importlib import import_module
import traceback

from alora.maestro.scheduleLib.genUtils import query_to_dict, MAESTRO_DIR

class ModuleManager:
    def __init__(self,write_out=print) -> None:
        self.write_out = write_out
        MODULE_DB_PATH = join(MAESTRO_DIR, "files","modules.db")
        self.module_db = sqlite3.connect(MODULE_DB_PATH)
        self.module_db.row_factory = sqlite3.Row

    def update_modules(self):
        self.module_db.cursor().execute('CREATE TABLE IF NOT EXISTS "modules" ("name" TEXT PRIMARY KEY, "modname" TEXT UNIQUE, "active" BOOLEAN, "description" TEXT, "author" TEXT, "dir" TEXT)')
        self.module_db.commit()
        existing_names = [row[0] for row in self.module_db.cursor().execute("SELECT name FROM modules").fetchall()]
        root = "schedulerConfigs"
        root_directory = join(MAESTRO_DIR, root)
        # to find modules, look for module.toml files in the schedulerConfigs directory, then add the name and dir to the db
        module_dirs = []
        module_tomls = glob.glob(join(root_directory, "**", "module.toml"), recursive=True)
        for toml in module_tomls:
            # module_names.append(module_name)
            module_dirs.append(dirname(toml))
        for dir in module_dirs:
            with open(join(dir,"module.toml"),"rb") as f:
                mod_info = tomlkit.load(f)
            try:
                name, description, author = mod_info["name"], mod_info["description"], mod_info["author"]
                # allow the module author to specify a different modname (used to locate and load the module) than the user-displayed name
                modname = mod_info.get("modname",name)
                # targets in the database will refer to the module's friendly name, not the modname
            except KeyError as e:
                self.write_out(f"Error reading module.toml in {dir}: missing key {e}. Skipping.")
                continue
            if name not in existing_names:
                self.module_db.cursor().execute(f"INSERT INTO modules (name, modname, active, description, author, dir) VALUES (?,?,?,?,?,?)", (name, modname, True, description, author, abspath(dir)))
            else:
                self.module_db.cursor().execute(f"UPDATE modules SET description = ?, author = ?, dir = ? WHERE name = ?", (description, author, abspath(dir), name))
            self.module_db.commit()
        
    def activate_module(self, name):
        self.module_db.cursor().execute("UPDATE modules SET active = 1 WHERE name = ?", (name,))
        self.module_db.commit()
    
    def deactivate_module(self, name):
        self.module_db.cursor().execute("UPDATE modules SET active = 0 WHERE name = ?", (name,))
        self.module_db.commit()
    
    def get_module_info(self, name):
        return self.module_db.cursor().execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    
    def list_modules(self):
        m = {}
        for d in query_to_dict(self.module_db.cursor().execute("SELECT * FROM modules").fetchall()):
            n = d.pop("name")
            m[n] = d
        return m
    
    def load_module(self, name, return_trace = False):
        mod_info = self.get_module_info(name)
        if not mod_info:
            self.write_out(f"Module {name} not found.")
            return None
        if not mod_info["active"]:
            self.write_out(f"Module {name} is not active.")
            return None
        modname = mod_info["modname"]
        try:
            if return_trace:
                return import_module(f"schedulerConfigs.{modname}", "schedulerConfigs"), None
            return import_module(f"schedulerConfigs.{modname}", "schedulerConfigs")
        except Exception as e:
            self.write_out(f"Error loading module {name}: {e}")
            if return_trace:
                return None, traceback.format_exc()
            return None
        
    def load_active_modules(self, include_failed = False):
        # this does two db queries when only one is necessary, but it's not a big deal
        active_modules = [k for k,mod in self.list_modules().items() if mod["active"]]
        if include_failed:
            return {mod: self.load_module(mod) for mod in active_modules}
        d = {}
        for mod in active_modules:
            m = self.load_module(mod)
            if m:
                d[mod] = m
        return d
            
    def load_all_modules(self):
        return {k: self.load_module(k) for k in self.list_modules()}