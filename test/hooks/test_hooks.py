import pytest
from hypothesis import given, settings

import schemathesis
from schemathesis.hooks import HookDispatcher


@pytest.fixture(params=["direct", "named"])
def global_hook(request):
    if request.param == "direct":

        @schemathesis.hooks.register
        def before_generate_query(context, strategy):
            return strategy.filter(lambda x: x["id"].isdigit())

    if request.param == "named":

        @schemathesis.hooks.register("before_generate_query")
        def hook(context, strategy):
            return strategy.filter(lambda x: x["id"].isdigit())

    yield
    schemathesis.hooks.unregister_all()


@pytest.fixture
def schema(flask_app):
    return schemathesis.from_wsgi("/swagger.yaml", flask_app)


@pytest.fixture()
def dispatcher():
    return HookDispatcher()


@pytest.mark.hypothesis_nested
@pytest.mark.endpoints("custom_format")
@pytest.mark.usefixtures("global_hook")
def test_global_query_hook(schema, schema_url):
    strategy = schema.endpoints["/api/custom_format"]["GET"].as_strategy()

    @given(case=strategy)
    @settings(max_examples=3)
    def test(case):
        assert case.query["id"].isdigit()

    test()


@pytest.mark.hypothesis_nested
@pytest.mark.endpoints("custom_format")
def test_schema_query_hook(schema, schema_url):
    @schema.hooks.register
    def before_generate_query(context, strategy):
        return strategy.filter(lambda x: x["id"].isdigit())

    strategy = schema.endpoints["/api/custom_format"]["GET"].as_strategy()

    @given(case=strategy)
    @settings(max_examples=3)
    def test(case):
        assert case.query["id"].isdigit()

    test()


@pytest.mark.hypothesis_nested
@pytest.mark.usefixtures("global_hook")
@pytest.mark.endpoints("custom_format")
def test_hooks_combination(schema, schema_url):
    @schema.hooks.register("before_generate_query")
    def extra(context, st):
        assert context.endpoint == schema.endpoints["/api/custom_format"]["GET"]
        return st.filter(lambda x: int(x["id"]) % 2 == 0)

    strategy = schema.endpoints["/api/custom_format"]["GET"].as_strategy()

    @given(case=strategy)
    @settings(max_examples=3)
    def test(case):
        assert case.query["id"].isdigit()
        assert int(case.query["id"]) % 2 == 0

    test()


def test_per_test_hooks(testdir, simple_openapi):
    testdir.make_test(
        """
from hypothesis import strategies as st

def replacement(context, strategy):
    return st.just({"id": "foobar"})

@schema.hooks.apply("before_generate_query", replacement)
@schema.parametrize()
@settings(max_examples=1)
def test_a(case):
    assert case.query["id"] == "foobar"

@schema.parametrize()
@schema.hooks.apply("before_generate_query", replacement)
@settings(max_examples=1)
def test_b(case):
    assert case.query["id"] == "foobar"

def another_replacement(context, strategy):
    return st.just({"id": "foobaz"})

def third_replacement(context, strategy):
    return st.just({"value": "spam"})

@schema.parametrize()
@schema.hooks.apply("before_generate_query", another_replacement)  # Higher priority
@schema.hooks.apply("before_generate_query", replacement)
@schema.hooks.apply("before_generate_headers", third_replacement)
@settings(max_examples=1)
def test_c(case):
    assert case.query["id"] == "foobaz"
    assert case.headers["value"] == "spam"

@schema.parametrize()
@settings(max_examples=1)
def test_d(case):
    assert case.query["id"] != "foobar"
    """,
        schema=simple_openapi,
    )
    result = testdir.runpytest()
    result.assert_outcomes(passed=4)


def test_hooks_via_parametrize(testdir, simple_openapi):
    testdir.make_test(
        """
@schema.hooks.register("before_generate_query")
def extra(context, st):
    return st.filter(lambda x: x["id"].isdigit() and int(x["id"]) % 2 == 0)

@schema.parametrize()
@settings(max_examples=1)
def test(case):
    assert case.endpoint.schema.hooks.get_hook("before_generate_query") is extra
    assert int(case.query["id"]) % 2 == 0
    """,
        schema=simple_openapi,
    )
    result = testdir.runpytest()
    result.assert_outcomes(passed=1)


def test_register_invalid_hook_name(dispatcher):
    with pytest.raises(TypeError, match="There is no hook with name 'hook'"):

        @dispatcher.register
        def hook():
            pass


def test_register_invalid_hook_spec(dispatcher):
    with pytest.raises(TypeError, match="Hook 'before_generate_query' takes 2 arguments but 3 is defined"):

        @dispatcher.register
        def before_generate_query(a, b, c):
            pass


def test_hook_noop(dispatcher):
    # When there is no registered hook under the given name
    # Then `dispatch` is no-op
    assert dispatcher.dispatch("before_generate_query") is None
