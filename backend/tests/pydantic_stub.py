"""
Minimal pydantic stub for testing in environments without pydantic installed.
Supports: BaseModel, field_validator, model_validator
This stub is imported by injecting it into sys.modules before importing services.
"""
import re


class FieldInfo:
    pass


def field_validator(*fields, mode="after"):
    """Decorator — runs validators in __init_subclass__ or __post_init__."""
    def decorator(fn):
        fn._is_field_validator = True
        fn._fields = fields
        fn._mode = mode
        return fn
    return decorator


def model_validator(mode="after"):
    def decorator(fn):
        fn._is_model_validator = True
        fn._mode = mode
        return fn
    return decorator


class ModelMetaclass(type):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        # Collect field validators and model validators
        cls._field_validators = {}
        cls._model_validators = []
        for attr_name, attr_val in namespace.items():
            if callable(attr_val):
                if getattr(attr_val, '_is_field_validator', False):
                    for f in attr_val._fields:
                        cls._field_validators.setdefault(f, []).append(attr_val)
                if getattr(attr_val, '_is_model_validator', False):
                    cls._model_validators.append(attr_val)
        # Inherit from base classes
        for base in bases:
            for f, validators in getattr(base, '_field_validators', {}).items():
                for v in validators:
                    cls._field_validators.setdefault(f, []).append(v)
            for v in getattr(base, '_model_validators', []):
                if v not in cls._model_validators:
                    cls._model_validators.append(v)
        return cls


class BaseModel(metaclass=ModelMetaclass):
    def __init__(self, **kwargs):
        import inspect
        # Apply defaults from annotations
        annotations = {}
        for klass in reversed(type(self).__mro__):
            annotations.update(getattr(klass, '__annotations__', {}))

        # Get class-level defaults
        for field, hint in annotations.items():
            if field.startswith('_'):
                continue
            if field in kwargs:
                val = kwargs[field]
            elif hasattr(type(self), field):
                default = getattr(type(self), field)
                if callable(default) and not isinstance(default, type):
                    val = default()
                else:
                    val = default
            else:
                val = None
            # Run field validators
            for validator in self._field_validators.get(field, []):
                try:
                    val = validator.__func__(type(self), val) if hasattr(validator, '__func__') else validator(type(self), val)
                except (ValueError, Exception):
                    raise
            setattr(self, field, val)

        # Run model validators
        for mv in self._model_validators:
            result = mv(self)
            if result is not None:
                pass  # model_validator returning self modifies in place

    def model_dump(self):
        annotations = {}
        for klass in reversed(type(self).__mro__):
            annotations.update(getattr(klass, '__annotations__', {}))
        result = {}
        for field in annotations:
            if not field.startswith('_'):
                result[field] = getattr(self, field, None)
        return result

    @classmethod
    def model_validate(cls, data):
        if isinstance(data, dict):
            return cls(**data)
        return data


class ValidationError(Exception):
    pass
