import inspect
import warnings
from typing import Any, Callable, Dict, Optional, Union, cast

import attr
from hypothesis import strategies as st

from .constants import HookLocation
from .models import Endpoint
from .types import Hook


def warn_deprecated_hook(hook: Hook) -> None:
    if "context" not in inspect.signature(hook).parameters:
        warnings.warn(
            DeprecationWarning(
                "Hook functions that do not accept `context` argument are deprecated and "
                "support will be removed in Schemathesis 2.0."
            )
        )


@attr.s(slots=True)  # pragma: no mutate
class HookContext:
    """A context that is passed to some hook functions."""

    endpoint: Endpoint = attr.ib()  # pragma: no mutate


@attr.s(slots=True)  # pragma: no mutate
class HookDispatcher:
    """Generic hook dispatcher.

    Provides a mechanism to extend Schemathesis in registered hook points.
    """

    _hooks: Dict = attr.ib(factory=dict)  # pragma: no mutate
    _specs: Dict[str, inspect.Signature] = {}  # pragma: no mutate

    def register(self, hook: Union[str, Callable]) -> Callable:
        """Register a new hook.

        Can be used as a decorator in two forms.
        Without arguments for registering hooks and autodetecting their names:

            @schema.hooks.register
            def before_generate_query(strategy, context):
                ...

        With a hook name as the first argument:

            @schema.hooks.register("before_generate_query")
            def hook(strategy, context):
                ...
        """
        if isinstance(hook, str):

            def decorator(func: Callable) -> Callable:
                hook_name = cast(str, hook)
                return self.register_hook_with_name(hook_name, func)

            return decorator
        return self.register_hook_with_name(hook.__name__, hook)

    def apply(self, name: str, hook: Callable) -> Callable[[Callable], Callable]:
        """Register hook to run only on one test function.

        Example:
            def hook(strategy, context):
                ...

            @schema.hooks.apply("before_generate_query", hook)
            @schema.parametrize()
            def test_api(case):
                ...

        """

        def decorator(func: Callable) -> Callable:
            if not hasattr(func, "_schemathesis_hooks"):
                func._schemathesis_hooks = self.__class__()  # type: ignore
            func._schemathesis_hooks.register_hook_with_name(name, hook)  # type: ignore
            return func

        return decorator

    def register_hook_with_name(self, name: str, hook: Callable, skip_validation: bool = False) -> Callable:
        """A helper for hooks registration.

        Besides its use in this class internally it is used to keep backward compatibility with the old hooks system.
        """
        # Validation is skipped only for backward compatibility with the old hooks system
        if not skip_validation:
            self._validate_hook(name, hook)
        self._hooks[name] = hook
        return hook

    @classmethod
    def register_spec(cls, spec: Callable) -> Callable:
        """Register hook specification.

        All hooks, registered with `register` should comply with corresponding registered specs.
        """
        cls._specs[spec.__name__] = inspect.signature(spec)
        return spec

    def _validate_hook(self, name: str, hook: Callable) -> None:
        """Basic validation for hooks being registered."""
        spec = self._specs.get(name)
        if spec is None:
            raise TypeError(f"There is no hook with name '{name}'")
        signature = inspect.signature(hook)
        if len(signature.parameters) != len(spec.parameters):
            raise TypeError(
                f"Hook '{name}' takes {len(spec.parameters)} arguments but {len(signature.parameters)} is defined"
            )

    def dispatch(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Find and execute a hook with provided arguments."""
        if name not in self._hooks:
            return None
        hook = self._hooks[name]
        return hook(*args, **kwargs)

    def get_hook(self, name: str) -> Optional[Callable]:
        """Get a hook by its name."""
        return self._hooks.get(name)

    def unregister_all(self) -> None:
        """Remove all registered hooks.

        Useful in tests.
        """
        self._hooks = {}


@HookDispatcher.register_spec
def before_generate_path_parameters(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


@HookDispatcher.register_spec
def before_generate_headers(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


@HookDispatcher.register_spec
def before_generate_cookies(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


@HookDispatcher.register_spec
def before_generate_query(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


@HookDispatcher.register_spec
def before_generate_body(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


@HookDispatcher.register_spec
def before_generate_form_data(strategy: st.SearchStrategy, context: HookContext) -> st.SearchStrategy:
    pass


GLOBAL_HOOK_DISPATCHER = HookDispatcher()
dispatch = GLOBAL_HOOK_DISPATCHER.dispatch
unregister_all = GLOBAL_HOOK_DISPATCHER.unregister_all


def register(*args: Union[str, Callable]) -> Callable:
    # This code suppose to support backward compatibility with the old hook system.
    # In Schemathesis 2.0 this function can be replaced with `register = GLOBAL_HOOK_DISPATCHER.register`
    if len(args) == 1:
        return GLOBAL_HOOK_DISPATCHER.register(args[0])
    if len(args) == 2:
        warnings.warn(
            "Calling `schemathesis.register` with two arguments is deprecated, use it as a decorator instead.",
            DeprecationWarning,
        )
        place, hook = args
        hook = cast(Callable, hook)
        warn_deprecated_hook(hook)
        if place not in HookLocation.__members__:
            raise KeyError(place)
        return GLOBAL_HOOK_DISPATCHER.register_hook_with_name(f"before_generate_{place}", hook, skip_validation=True)
    # This approach is quite naive, but it should be enough for the common use case
    raise TypeError("Invalid number of arguments. Please, use `register` as a decorator.")
