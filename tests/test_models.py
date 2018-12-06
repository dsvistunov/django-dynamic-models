import datetime
from functools import partial
import pytest
from django.db import models
from django.utils import timezone

from dynamic_models import exceptions
from dynamic_models.schema import ModelSchemaChecker
from dynamic_models.models import DynamicModelField
from dynamic_models.utils import (
    db_table_exists, db_table_has_field, db_field_allows_null, is_registered
)
from .models import ModelSchema, FieldSchema

# pylint: disable=unused-argument,redefined-outer-name

class CleanUp:
    def clean_up_table(self, model_schema):
        if db_table_exists(model_schema.table_name):
            model_schema.schema_editor.drop()


@pytest.mark.django_db
class TestModelSchemaEditor(CleanUp):

    @pytest.fixture
    def model_schema(self):
        return ModelSchema(name='simple model')

    @pytest.fixture
    def existing_table(self, model_schema):
        model_schema.schema_editor.create()
        try:
            yield
        finally:
            self.clean_up_table(model_schema)

    def test_table_schema_exists(self, model_schema):
        assert not model_schema.schema_editor.exists()
        model_schema.schema_editor.create()
        assert model_schema.schema_editor.exists()

    def test_create_table_schema(self, model_schema):
        assert not db_table_exists(model_schema.table_name)
        model_schema.schema_editor.create()
        assert db_table_exists(model_schema.table_name)
        self.clean_up_table(model_schema)

    @pytest.mark.usefixtures("existing_table")
    def test_drop_table_schema(self, model_schema):
        model_schema.schema_editor.drop()
        assert not db_table_exists(model_schema.table_name), "table not dropped"

    @pytest.mark.usefixtures("existing_table")
    def test_alter_table_schema(self, model_schema):
        intial_table_name = model_schema.table_name
        model_schema.name = 'different name'
        model_schema.schema_editor.alter()
        assert not db_table_exists(intial_table_name), "old table still exists"
        assert db_table_exists(model_schema.table_name), "new table does not exist"


@pytest.mark.django_db
class TestFieldSchemaEditor(CleanUp):

    @pytest.fixture
    def field_schema(self, model_schema, int_field_schema):
        return DynamicModelField(model=model_schema, field=int_field_schema)

    @pytest.fixture
    def existing_column(self, model_schema, field_schema):
        field_schema.schema_editor.create()
        try:
            yield
        finally:
            self.clean_up_table(model_schema)

    def test_field_schema_exists(self, model_schema, field_schema):
        assert not field_schema.schema_editor.exists()
        field_schema.schema_editor.create()
        assert field_schema.schema_editor.exists()

    def test_create_field_schema(self, model_schema, field_schema):
        has_field = partial(db_table_has_field, model_schema.table_name)
        assert not has_field(field_schema.column_name), "field already present"
        field_schema.schema_editor.create()
        assert has_field(field_schema.column_name), "field not added"
        self.clean_up_table(model_schema)

    @pytest.mark.usefixtures("existing_column")
    def test_drop_field_schema(self, model_schema, field_schema):
        has_field = partial(db_table_has_field, model_schema.table_name)
        assert has_field(field_schema.column_name), "field does not exist initially"
        field_schema.schema_editor.drop()
        assert not has_field(field_schema.column_name), "field not dropped"

    @pytest.mark.usefixtures("existing_column")
    def test_alter_field_schema(self, model_schema, field_schema):
        has_field = partial(db_table_has_field, model_schema.table_name)
        initial_field_name = field_schema.column_name
        assert has_field(initial_field_name), "field not added correctly"

        field_schema.field.name = 'different name'
        field_schema.schema_editor.alter()
        assert not has_field(initial_field_name), "old field still exists"
        assert has_field(field_schema.column_name), "new field does not exist"


class TestModelSchemaChecker:

    def update_schema_timestamp(self, schema):
        schema.modified = timezone.now()
        schema.schema_checker.update()

    def test_outdated_model_is_updated_automatically(self, model_schema):
        checker = model_schema.schema_checker
        original_model = model_schema.as_model()
        assert checker.is_current(original_model), "model should be current"

        self.update_schema_timestamp(model_schema)
        assert not checker.is_current(original_model),\
            "model should no longer be current"
       
        new_model = model_schema.as_model()
        assert checker.is_current(new_model), "model should again be current"

    def test_delete_last_modified(self, model_schema):
        checker = model_schema.schema_checker
        assert checker.get_last_modified()
        checker.delete()
        assert checker.get_last_modified() is None
        