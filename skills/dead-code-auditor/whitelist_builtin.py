# Built-in whitelist for common Python ML project patterns
# These are false positives that appear across many projects
#
# Format: one name per line, optional comment explaining the pattern

# ============================================================================
# Pytest patterns
# ============================================================================
# pytest fixtures are used via dependency injection
conftest  # pytest configuration module
pytest_plugins  # pytest plugin registration

# ============================================================================
# Dataclass / Pydantic / attrs patterns
# ============================================================================
# Fields accessed via serialization or attribute access
__post_init__  # dataclass post-init hook
__init_subclass__  # class customization hook
model_config  # Pydantic v2 configuration
Config  # Pydantic v1 configuration class
__get_validators__  # Pydantic custom type validators
__modify_schema__  # Pydantic schema modification

# ============================================================================
# SQLAlchemy / ORM patterns
# ============================================================================
__tablename__  # SQLAlchemy table name
__table_args__  # SQLAlchemy table arguments
metadata  # SQLAlchemy metadata

# ============================================================================
# Click / Typer CLI patterns
# ============================================================================
# CLI functions are registered and called externally
main  # Common CLI entry point name
cli  # Common CLI group name
app  # Common Typer app name

# ============================================================================
# Flask / FastAPI / Web framework patterns
# ============================================================================
# Route handlers are called by the framework
create_app  # Flask factory pattern
lifespan  # FastAPI lifespan handler
startup  # ASGI startup event
shutdown  # ASGI shutdown event

# ============================================================================
# Celery / Task queue patterns
# ============================================================================
# Tasks are called via message queue
celery_app  # Celery application instance

# ============================================================================
# Logging patterns
# ============================================================================
logger  # Module-level logger (may only be used in some code paths)
log  # Alternative logger name

# ============================================================================
# Type checking patterns
# ============================================================================
# Used only during type checking
TYPE_CHECKING  # typing module constant
Protocol  # typing Protocol base class

# ============================================================================
# Dunder methods that may appear unused
# ============================================================================
__all__  # Module exports
__version__  # Package version
__author__  # Package author
__license__  # Package license
__repr__  # Object representation (called by Python)
__str__  # String representation (called by Python)
__hash__  # Hash function (called by Python)
__eq__  # Equality comparison (called by Python)
__lt__  # Less than comparison (called by Python)
__le__  # Less than or equal (called by Python)
__gt__  # Greater than (called by Python)
__ge__  # Greater than or equal (called by Python)
__len__  # Length (called by Python)
__iter__  # Iterator (called by Python)
__next__  # Next item (called by Python)
__enter__  # Context manager enter (called by Python)
__exit__  # Context manager exit (called by Python)
exc_type  # Context manager __exit__ parameter (protocol-required)
exc_val  # Context manager __exit__ parameter (protocol-required)
exc_tb  # Context manager __exit__ parameter (protocol-required)
__call__  # Callable (called by Python)
__getitem__  # Item access (called by Python)
__setitem__  # Item assignment (called by Python)
__contains__  # Membership test (called by Python)

# ============================================================================
# Common utility function names that may be entry points
# ============================================================================
run  # Generic run function
execute  # Generic execute function
process  # Generic process function
handle  # Generic handler function

# ============================================================================
# ML/Data Science patterns
# ============================================================================
# Scikit-learn compatible API
fit  # Scikit-learn fit method
transform  # Scikit-learn transform method
fit_transform  # Scikit-learn fit_transform method
predict  # Scikit-learn predict method
predict_proba  # Scikit-learn predict_proba method
score  # Scikit-learn score method
get_params  # Scikit-learn get_params method
set_params  # Scikit-learn set_params method

# PyTorch patterns
forward  # PyTorch forward pass
training_step  # PyTorch Lightning training step
validation_step  # PyTorch Lightning validation step
test_step  # PyTorch Lightning test step
configure_optimizers  # PyTorch Lightning optimizer config

# ============================================================================
# Flyte workflow patterns
# ============================================================================
# Flyte tasks and workflows are called by the Flyte runtime
