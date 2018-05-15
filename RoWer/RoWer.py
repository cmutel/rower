from bw2data.backends.peewee import ActivityDataset as AD
from collections import defaultdict
from time import time
import bw2data
import json
import os
import shutil
import sys


class Rower(object):
    def __init__(self, database):
        """Initiate ``Rower`` object to consistently label 'Rest-of-World' locations in LCI databases.

        ``database`` must be a registered database."""
        assert database in bw2data.databases, "Database {} not registered".format(database)
        self.db = bw2data.Database(database)

    def define_RoWs(modify_db_in_place=True, verbose=True):
        """Generate and return "RoW definition" dict and "activities to new RoW" dict.

        "RoW definition" identifies the geographies that are to be **excluded** from the RoW.
        It has the structure {'RoW_0': ['geo1', 'geo2', ..., ], 'RoW_1': ['geo3', 'geo4', ..., ]}.

        The "activities to new RoW" dict identifies which activities have which each RoW.
        It has the structure {'RoW_0': ['code of activity', 'code of another activity']}

        If ``modify_db_in_place`` is ``True``, the activities in ``self.db``
        will be labeled with the new RoW labels.

        If ``verbose`` is ``True``, some status information is printed to the
        console.

        """
        start = time()
        loaded_db = bw2data.Database(database).load()
        acts_with_RoWs = [act for act, data in loaded_db.items() if data['location']=='RoW']
        if len(acts_with_RoWs) == 0:
            print("No datasets with RoW location found. Exiting.")
            sys.exit()
        if verbose:
            print("{} activities with RoW location found in {:4} seconds, generating dictionaries".format(
                len(acts_with_RoWs),
                time()-t0
            )
            )
        t1 = time()

        RoW_dict = {}         # RoW definitions
        activity_mapping = {} # RoW to activities

        for i, act in enumerate(acts_with_RoWs):
            RoW_dict['RoW_' + str(i)] = [data['location'] for data in loaded_db.values()
                                         if data['name'] == loaded_db[act]['name']
                                         and data['reference product'] == loaded_db[act]['reference product']
                                         and data['location'] != 'RoW'
                                         ]
            RoW_act_mapping[act] = 'RoW_' + str(i)
        if verbose:
            print("Generated {} RoW definitions in {:4} seconds".format(
                len(RoW_dict),
                time()-t1
            )
            )
        if modify_db_in_place:
            print("Modifying database {} in place".format(database))
            modify_database_from_loaded_database(database, loaded_db, RoW_act_mapping)
        return RoW_dict, RoW_act_mapping

    def _define_RoWs_sqlite(self, modify, verose):
        qs = list(AD.select(AD.name, AD.product, AD.location, AD.code).where(
            AD.database == self.db.name).dicts())
        base = defaultdict(list)
        for obj in qs:
            base[(obj['name'], obj['product'])].append((obj['location'], obj['code']))
        grouped = defaultdict(set)
        for obj in base.values():
            if not any(x[0] == 'RoW' for x in obj):
                continue
            grouped[sorted([x[0] for x in obj])].update({x[1] for x in obj})
        RoWs = {"RoW_{}".format(i): key for i, key in enumerate(sorted(grouped))}

        grouped = {: [x[1] for x in lst] for lst in base.values()}
        RoWs = sorted(
            [v for v in grouped.values() if any(x[0] == 'RoW' for x in v)],
            key=lambda obj: sorted([x[0] for x in obj])
        )


        grouper = lambda x: (x['name'], x['product'])
        for group in groupby(grouper, qs):
            break

    data = PickleField()             # Canonical, except for other C fields
    code = TextField()               # Canonical
    database = TextField()           # Canonical
    location = TextField(null=True)  # Reset from `data`
    name = TextField(null=True)      # Reset from `data`
    product = TextField(null=True)   # Reset from `data`
    type = TextField(null=True)      # Reset from `data`


def modify_database_from_stored_database(database_name, RoW_act_mapping):
    """ Specify RoW locations in a database on disk and save database"""
    assert database_name in bw2data.databases, "Database {} not registered".format(database)
    modify_database_from_loaded_database(
        database_name,
        Database(database_name).load(),
        RoW_act_mapping
    )
    return None


def modify_database_from_loaded_database(database_name, loaded_database, RoW_act_mapping):
    """ Specify RoW locations in a loaded database and save database to disk"""
    for act, new_row in RoW_act_mapping.items():
        loaded_database[act]['location'] = new_row
    bw2data.Database(database_name).write(loaded_database)


def write_RoW_info(RoW_dict, RoW_act_mapping, root_dirpath=None, overwrite=False, new_name=None):
    """ Function to store RoW data to disk.

    Will create a directory following the json Data Package schema.
    By default, the name of the Data Package is the name of the database, i.e.
    the first string in the key of the activities.
    It is possible to override this default name with `new_name`, but you should probably
    not do this.
    The data package will have two resources:
        RoW definition dict
        activities to new RoW dict
    """
    # Check that there is actually some data to save
    assert len(RoW_dict)>0, "No data to save"
    # Validate dicts:
    assert len(RoW_dict)==len(RoW_act_mapping), "The two dicts must have the same length"
    implicit_db_names = [key[0] for key in RoW_act_mapping.keys()]
    assert len(set(implicit_db_names))==1, "The dicts should be for a single database"
    implicit_db_name = implicit_db_names[0]
    name = new_name or implicit_db_name

    if root_dirpath is None:
        root_dirpath = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data")

    if os.path.exists(root_dirpath):
        assert os.path.isdir(root_dirpath), "`root_dirpath` must be a directory"
        assert os.access(root_dirpath, os.W_OK), "`dirpath` must be a writable directory"
    else:
        os.makedirs(root_dirpath)

    dirpath = os.path.join(root_dirpath, name)

    if os.path.isdir(dirpath):
        if not overwrite:
            raise ValueError("The directory {} already exists".format(dirpath))
        else:
            shutil.rmtree(dirpath)
    os.makedirs(dirpath)

    # Inform datapackage metadata
    datapackage = {
        "name": str(name),
        "description": "Dictionaries containing details about RoWs for database {}".format(implicit_db_name),
        "profile": "data-package",
        "resources": [
            {"RoW definitions":
                {
                    "name": "RoW definition dict",
                    "path": os.path.join(dirpath, 'RoW_definition.json'),
                    "description": "Dictionary with specific RoWs as keys and list of excluded geographies as value.",
                    "format": "json",
                }
            },
            {"Mapping":
                 {
                    "name": "Activity to RoW mapping dict",
                    "path": os.path.join(dirpath, 'activity_to_RoW_mapping.json'),
                    "description": "Dictionary mapping activity codes to specific RoWs.",
                    "format": "json",
                },
            }
        ]
    }

    RoW_act_mapping_as_codes = {k[1]:v for k, v in RoW_act_mapping.items()}

    with open(os.path.join(dirpath, "datapackage.json"), "w", encoding='utf-8') as f:
        json.dump(datapackage, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dirpath, "RoW_definition.json"), "w", encoding='utf-8') as f:
        json.dump(RoW_dict, f, indent=2, ensure_ascii=False)
    with open(os.path.join(dirpath, "activity_to_RoW_mapping.json"), "w", encoding='utf-8') as f:
        json.dump(RoW_act_mapping_as_codes, f, indent=2, ensure_ascii=False)
