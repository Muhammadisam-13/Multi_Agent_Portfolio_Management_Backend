"""A small JSON-schema checker for model replies (no new dependency; `jsonschema` is not in requirements.txt).

Supports the keywords our schemas use: type, properties, required, additionalProperties (true/false), items, enum, const,
minLength, maxLength, minimum, maximum, minItems, maxItems. Annotations (title, description, $schema) are ignored.
Any other keyword raises ValueError, so a schema we cannot check is never silently treated as passed.
"""

_ANNOTATIONS = {"title", "description", "$schema", "examples", "default"}
_SUPPORTED = {"type", "properties", "required", "additionalProperties", "items", "enum", "const",
              "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"} | _ANNOTATIONS

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def schema_errors(value, schema: dict, path: str = "$") -> list[str]:
    """Every way `value` breaks `schema`, as short readable strings. Empty list: it matches."""
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise ValueError(f"schema keyword(s) not supported by schema_check: {', '.join(sorted(unknown))}")
    if not isinstance(schema.get("additionalProperties", True), bool):
        raise ValueError("schema_check supports additionalProperties only as true or false")
    errors: list[str] = []

    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](value) for t in allowed):
            return [f"{path}: expected {' or '.join(allowed)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")
        for key, sub in value.items():
            if key in props:
                errors.extend(schema_errors(sub, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{path}: unexpected field '{key}'")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, sub in enumerate(value):
                errors.extend(schema_errors(sub, schema["items"], f"{path}[{i}]"))
    return errors
