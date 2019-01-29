from peewee import *
from peewee import chunked
import os
from playhouse.shortcuts import model_to_dict, dict_to_model
import json
import csv
cwd=os.getcwd()
DATABASE=cwd+'/data/keys.db'
database = SqliteDatabase(DATABASE)
class BaseModel(Model):
    class Meta:
        database = database
#Keys bean
class Keys (BaseModel):
    name=CharField(primary_key=True)
    keyval=FloatField(null=False)
    created_at=DateTimeField(null=False)
    transbounds=CharField(null=False)
    def to_json(self):
        return json.dumps(model_to_dict(self))
    def to_dict(self):
        return model_to_dict(self)




