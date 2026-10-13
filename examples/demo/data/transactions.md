# Durable transactions

A transaction groups storage changes so they commit together. A failed rebuild
should leave the previously published index usable. SQLite can store tables
and indexes in one database file. Parameterized SQL keeps values separate from
statements. Close readers before replacing a database file on Windows.
