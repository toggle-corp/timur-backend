import time
import typing

from graphql import get_introspection_query

from apps.api_token.factories import ApiTokenFactory
from apps.user.factories import UserFactory
from main.graphql.limits import MAX_ALIASES, MAX_INTROSPECTION_DEPTH, MAX_QUERY_DEPTH, MAX_TOKENS
from main.tests import TestCase


def fragment_chain(levels: int, leaf: str = "__typename") -> str:
    """
    `F0` spreads `F1` three times, `F1` spreads `F2` three times, ...: `3 ** levels` leaves once fully expanded.
    """
    fragments = [f"fragment F{i} on Query {{ ...F{i + 1} ...F{i + 1} ...F{i + 1} }}" for i in range(levels)]
    fragments.append(f"fragment F{levels} on Query {{ {leaf} }}")
    return "query Chain { ...F0 } " + " ".join(fragments)


class TestQueryLimits(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.force_login(UserFactory.create())

    def _errors(self, query: str, **kwargs) -> list[str]:
        response = self.client.post(
            "/graphql/",
            data={"query": query},
            content_type="application/json",
            **kwargs,
        )
        return [error["message"] for error in response.json().get("errors", [])]

    def test_alias_limit(self):
        def query(count: int) -> str:
            return "query { " + " ".join(f"a{i}: __typename" for i in range(count)) + " }"

        assert self._errors(query(MAX_ALIASES)) == []
        assert self._errors(query(MAX_ALIASES + 1)) == [f"{MAX_ALIASES + 1} aliases found. Allowed: {MAX_ALIASES}"]

    def test_depth_limit(self):
        def query(depth: int) -> str:
            # The depth limit is checked on the document only, so unknown fields are enough here
            return "query Deep { " + "a { " * depth + "b" + " }" * depth + " }"

        message = f"'Deep' exceeds maximum operation depth of {MAX_QUERY_DEPTH}"
        assert message not in self._errors(query(MAX_QUERY_DEPTH))
        assert message in self._errors(query(MAX_QUERY_DEPTH + 1))

    def test_depth_counts_fragments(self):
        def query(depth: int) -> str:
            return "query Deep { ...F } fragment F on Query { " + "a { " * depth + "b" + " }" * depth + " }"

        message = f"'Deep' exceeds maximum operation depth of {MAX_QUERY_DEPTH}"
        assert message not in self._errors(query(MAX_QUERY_DEPTH))
        assert message in self._errors(query(MAX_QUERY_DEPTH + 1))

    def test_aliases_counted_per_fragment_spread(self):
        fragment = "fragment F on PublicQuery { a1: id a2: id a3: id a4: id }"

        def query(spreads: int) -> str:
            # One unaliased `public` plus aliased ones, each spreading F (4 aliases)
            parents = ["public { ...F }", *(f"p{i}: public {{ ...F }}" for i in range(1, spreads))]
            return "query { " + " ".join(parents) + " } " + fragment

        assert self._errors(query(3)) == []  # 2 + 3 * 4 = 14
        assert self._errors(query(4)) == [f"19 aliases found. Allowed: {MAX_ALIASES}"]  # 3 + 4 * 4

    def test_fragment_chain_is_measured_in_linear_time(self):
        """
        Expanding a fragment chain is exponential; each fragment is measured once instead.
        """
        levels = 38  # Close to the token limit
        started = time.monotonic()
        assert self._errors(fragment_chain(levels)) == []
        aliased_errors = self._errors(fragment_chain(levels, leaf="a: __typename"))
        assert time.monotonic() - started < 2
        assert aliased_errors == [f"{3**levels} aliases found. Allowed: {MAX_ALIASES}"]

    def test_limit_errors_have_code(self):
        response = self.client.post(
            "/graphql/",
            data={"query": "query { " + " ".join(f"a{i}: __typename" for i in range(MAX_ALIASES + 1)) + " }"},
            content_type="application/json",
        )
        assert response.json()["errors"][0]["extensions"] == {"code": "limit_exceeded", "limit": "aliases"}

    def test_deepest_real_query_allowed(self):
        assert (
            self._errors(
                """
                query {
                  private {
                    myTimeEntries(date: "2024-01-01") {
                      task {
                        contract {
                          project {
                            projectClient {
                              createdBy {
                                id
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
                """,
            )
            == []
        )

    def test_token_limit(self):
        def query(token_count: int) -> str:
            # `query { __typename ... }`: 3 tokens around the fields
            return "query { " + " ".join(["__typename"] * (token_count - 3)) + " }"

        assert self._errors(query(MAX_TOKENS)) == []
        errors = self._errors(query(MAX_TOKENS + 1))
        assert len(errors) == 1
        assert f"more than {MAX_TOKENS} tokens" in errors[0]

    def test_introspection_allowed(self):
        for query in [
            get_introspection_query(),
            get_introspection_query(
                descriptions=True,
                specified_by_url=True,
                directive_is_repeatable=True,
                schema_description=True,
                input_value_deprecation=True,
            ),
        ]:
            assert self._errors(query) == []

    def test_graphql_js_introspection_query_allowed(self):
        """
        graphql-js 16 `getIntrospectionQuery` with every option graphql-core supports (codegen, GraphiQL).
        """
        query = """
            query IntrospectionQuery {
              __schema {
                description queryType { name } mutationType { name } subscriptionType { name }
                types { ...FullType }
                directives { name description isRepeatable locations args(includeDeprecated: true) { ...InputValue } }
              }
            }
            fragment FullType on __Type {
              kind name description specifiedByURL
              fields(includeDeprecated: true) {
                name description args(includeDeprecated: true) { ...InputValue } type { ...TypeRef }
                isDeprecated deprecationReason
              }
              inputFields(includeDeprecated: true) { ...InputValue }
              interfaces { ...TypeRef }
              enumValues(includeDeprecated: true) { name description isDeprecated deprecationReason }
              possibleTypes { ...TypeRef }
            }
            fragment InputValue on __InputValue {
              name description type { ...TypeRef } defaultValue isDeprecated deprecationReason
            }
            fragment TypeRef on __Type {
              kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType {
                kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
              } } } } }
            }
        """
        assert self._errors(query) == []

    def test_nested_introspection_lists_rejected(self):
        query = "query { __schema { types { fields { type { fields { type { fields { name } } } } } } } }"
        assert self._errors(query) == ["Maximum introspection depth exceeded"]
        query = "query { __type(name: \"Query\") { fields { type { fields { type { fields { name } } } } } } }"
        assert self._errors(query) == ["Maximum introspection depth exceeded"]
        # Two nested lists (as in the standard introspection query) are fine
        assert self._errors("query { __schema { types { fields { type { fields { name } } } } } }") == []

    def test_deep_introspection_rejected(self):
        def query(depth: int) -> str:
            # __type(1) > ofType ... > name
            return 'query { __type(name: "Query") { ' + "ofType { " * (depth - 1) + "name" + " }" * depth + " }"

        assert self._errors(query(MAX_INTROSPECTION_DEPTH)) == []
        assert self._errors(query(MAX_INTROSPECTION_DEPTH + 1)) == ["Maximum introspection depth exceeded"]

    def test_broken_fragments_rejected_by_validation(self):
        for query in [
            "query { ...A } fragment A on Query { ...B } fragment B on Query { ...A }",
            "query { ...Missing }",
        ]:
            errors = self._errors(query)
            assert errors, query
            assert not any("recursion" in message for message in errors), errors

    def test_deeply_nested_document_rejected_by_token_limit(self):
        depth = MAX_TOKENS // 3
        errors = self._errors("{" + "a {" * depth + "b" + "}" * depth + "}")
        assert errors == ["Syntax Error: Document contains more than 500 tokens. Parsing aborted."]

    def test_limits_apply_to_tokens(self):
        token = ApiTokenFactory.create()
        query = "query { " + " ".join(f"a{i}: __typename" for i in range(MAX_ALIASES + 1)) + " }"
        assert self._errors(query, HTTP_AUTHORIZATION=f"Bearer {token.secret}") == [
            f"{MAX_ALIASES + 1} aliases found. Allowed: {MAX_ALIASES}",
        ]
