from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from collections import OrderedDict

import datetime
from pytest import raises
import sqlalchemy.exc
import sqlalchemy.dialects.postgresql
import six
from copy import deepcopy

from sqlbag import temporary_database, S, quoted_identifier

import schemainspect
from schemainspect import get_inspector
from schemainspect.inspected import ColumnInfo
from schemainspect.pg import InspectedIndex, InspectedSequence, InspectedConstraint, InspectedExtension

from common import db  # flake8: noqa

if not six.PY2:
    unicode = str

T_CREATE = """create table "public"."films" (
    "code" character(5) not null,
    "title" character varying not null,
    "did" bigint not null,
    "date_prod" date,
    "kind" character varying(10),
    "len" interval hour to minute,
    "drange" daterange
);
"""

CV = 'character varying'
CV10 = 'character varying(10)'
INT = 'interval'
INTHM = 'interval hour to minute'
PGRANGE = sqlalchemy.dialects.postgresql.ranges.DATERANGE
TD = datetime.timedelta


FILMS_COLUMNS = OrderedDict([
    ('code', ColumnInfo(
        'code', 'character', str, dbtypestr='character(5)')),
    ('title', ColumnInfo('title', 'character varying', str)),
    ('did', ColumnInfo('did', 'bigint', int)),
    ('date_prod', ColumnInfo('date_prod', 'date', datetime.date)),
    ('kind', ColumnInfo('kind', CV, str, dbtypestr=CV10)),
    ('len', ColumnInfo('len', INT, TD, dbtypestr=INTHM)),
    (u'drange', ColumnInfo('drange', 'daterange', PGRANGE))
])

FILMSF_COLUMNS = OrderedDict([
    ('title', ColumnInfo('title', 'character varying', str)),
    ('release_date', ColumnInfo('release_date', 'date', datetime.date))
])

d1 = ColumnInfo('d', 'date', datetime.date)
d2 = ColumnInfo('def_t', 'text', str, default='NULL::text')
d3 = ColumnInfo('def_d', 'date', datetime.date, default="'2014-01-01'::date")
FILMSF_INPUTS = [d1, d2, d3]

FDEF = """create or replace function public.films_f(d date, def_t text, def_d date)
returns TABLE(title character varying, release_date date) as
$$select 'a'::varchar, '2014-01-01'::date$$
LANGUAGE SQL;
"""

VDEF = """create view "public"."v_films" as  SELECT films.code,
    films.title,
    films.did,
    films.date_prod,
    films.kind,
    films.len,
    films.drange
   FROM films;
"""

MVDEF = """create materialized view "public"."mv_films" as  SELECT films.code,
    films.title,
    films.did,
    films.date_prod,
    films.kind,
    films.len,
    films.drange
   FROM films;
"""


def test_basic_schemainspect():
    a = ColumnInfo('a', 'text', str)
    a2 = ColumnInfo('a', 'text', str)

    b = ColumnInfo('b', 'text', str, dbtypestr='text')
    b2 = ColumnInfo('b', 'text', str, dbtypestr='text', default="'d'::text")

    assert a == a2
    assert hash(a) == hash(a)
    assert hash(a) != hash(b)
    assert a != b
    assert b != b2

    with temporary_database('sqlite') as dburl:
        with raises(NotImplementedError):
            with S(dburl) as s:
                get_inspector(s)


def test_inspected():
    x = schemainspect.Inspected()
    x.name = 'b'
    x.schema = 'a'
    assert x.quoted_full_name == '"a"."b"'
    assert x.unquoted_full_name == 'a.b'

    x = schemainspect.ColumnInfo(name='a', dbtype='integer', pytype=int)
    assert x.creation_sql == '"a" integer'
    x.default = "5"
    x.not_null = True
    assert x.creation_sql == '"a" integer not null default 5'


def test_postgres_objects():
    ex = InspectedExtension('name', 'schema', '1.2')
    assert ex.drop_statement == 'drop extension if exists "name";'
    assert ex.create_statement == \
        'create extension "name" with schema "schema" version \'1.2\';'
    assert ex.update_statement == \
        'alter extension "schema"."name" update to version \'1.2\';'

    ex2 = deepcopy(ex)
    assert ex == ex2
    ex2.version = '2.1'
    assert ex != ex2

    ix = InspectedIndex('name', 'schema', 'table', 'create index name on t(x)')
    assert ix.drop_statement == 'drop index "schema"."name";'
    assert ix.create_statement == \
        'create index name on t(x);'

    ix2 = deepcopy(ix)
    assert ix == ix2
    ix2.definition = 'create index name on t(y)'
    assert ix != ix2

    i = InspectedSequence('name', 'schema')
    assert i.create_statement == 'create sequence "schema"."name";'
    assert i.drop_statement == 'drop sequence "schema"."name";'
    i2 = deepcopy(i)
    assert i == i2
    i2.schema = 'schema2'
    assert i != i2

    c = InspectedConstraint(
        constraint_type='PRIMARY KEY',
        definition='PRIMARY KEY (code)',
        is_index=True,
        name='firstkey',
        schema='public',
        table_name='films')

    assert c.create_statement == \
        'alter table "public"."films" add constraint "firstkey" PRIMARY KEY using index "firstkey";'

    c2 = deepcopy(c)
    assert c == c2
    c.is_index = False
    assert c != c2
    assert c.create_statement == 'alter table "public"."films" add constraint "firstkey" PRIMARY KEY (code);'
    assert c.drop_statement == 'alter table "public"."films" drop constraint "firstkey";'


def setup_pg_schema(s):
    s.execute('create extension pg_trgm')

    s.execute("""
        CREATE TABLE films (
            code        char(5) CONSTRAINT firstkey PRIMARY KEY,
            title       varchar NOT NULL,
            did         bigint NOT NULL,
            date_prod   date,
            kind        varchar(10),
            len         interval hour to minute,
            drange      daterange
        );
    """)

    s.execute("""CREATE VIEW v_films AS (select * from films)""")

    s.execute("""
            CREATE MATERIALIZED VIEW mv_films
            AS (select * from films)
        """)

    s.execute("""
            CREATE or replace FUNCTION films_f(d date,
            def_t text default null,
            def_d date default '2014-01-01'::date)
            RETURNS TABLE(
                title character varying,
                release_date date
            )
            as $$select 'a'::varchar, '2014-01-01'::date$$
            language sql;
        """)

    s.execute("""
        CREATE OR REPLACE FUNCTION inc_f(integer) RETURNS integer AS $$
        BEGIN
                RETURN i + 1;
        END;
        $$ LANGUAGE plpgsql stable;
    """)

    s.execute("""
            create index on films(title);
        """)


def asserts_pg(i):
    def n(name, schema='public'):
        return '{}.{}'.format(
            quoted_identifier(schema), quoted_identifier(name))

    assert i.dialect.name == 'postgresql'

    v_films = n('v_films')
    v = i.views[v_films]

    public_views = {k: v for k, v in i.views.items() if v.schema == 'public'}

    assert list(public_views.keys()) == [v_films]
    assert v.columns == FILMS_COLUMNS
    assert v.create_statement == VDEF
    assert v == v
    assert v == deepcopy(v)
    assert v.drop_statement == \
        'drop view if exists {} cascade;'.format(v_films)

    mv_films = n('mv_films')
    mv = i.materialized_views[mv_films]
    assert list(i.materialized_views.keys()) == [mv_films]
    assert mv.columns == FILMS_COLUMNS
    assert mv.create_statement == MVDEF
    assert mv.drop_statement == \
        'drop materialized view if exists {} cascade;'.format(mv_films)

    films_f = n('films_f')
    inc_f = n('inc_f')
    public_funcs = \
        [k for k, v in i.functions.items() if v.schema == 'public']
    assert public_funcs == [films_f, inc_f]
    f = i.functions[films_f]

    assert f.columns == FILMSF_COLUMNS

    assert f.inputs == FILMSF_INPUTS

    fdef = i.functions[films_f].definition
    assert fdef == "select 'a'::varchar, '2014-01-01'::date"
    assert f.create_statement == FDEF
    assert f.drop_statement == \
        'drop function if exists public.films_f(d date, def_t text, def_d date) cascade;'

    assert [e.quoted_full_name for e in i.extensions.values()] == \
        [n('plpgsql', schema='pg_catalog'), n('pg_trgm')]

    cons = i.constraints[n('firstkey')]
    assert cons.create_statement == 'alter table "public"."films" add constraint "firstkey" PRIMARY KEY using index "firstkey";'

    t_films = n('films')
    t = i.tables[t_films]
    assert t.create_statement == T_CREATE
    assert t.drop_statement == 'drop table {};'.format(t_films)


def test_postgres_inspect(db):
    with S(db) as s:
        setup_pg_schema(s)
        i = get_inspector(s)
        asserts_pg(i)