# The Tessel library index

The libraries published for [Tessel](https://tessel-lang.syncster.dev)
programs. Each published version is one file,
`packages/<name>/<version>.toml`, that says where its code is (a tag of
its git repository, and the commit and checksum it had when published)
and which libraries it uses. The code itself stays in its own repository.

Browse them at **[tessel-packages.syncster.dev](https://tessel-packages.syncster.dev)**,
which is rebuilt from this repository whenever a version is merged
(`site/`).

## Using a library

```sh
tessel search            # what's here
tessel add textkit       # use one in your project
```

then `import textkit` in the code. See
[Libraries](https://tessel-lang.syncster.dev/guides/libraries/).

## Publishing a library

In the library's folder (its git repository, with a `tessel.toml` that
has a `[library]` table):

```sh
tessel publish
```

It checks the library, tags the commit, pushes the tag, and opens the page
that proposes the version's file here as a pull request. The pull request
is checked automatically (`tessel publish --check`):

- the file is in `packages/<name>/<version>.toml` and is well formed;
- it's a new file (a published version never changes);
- the name belongs to the same repository as its earlier versions;
- the tag names the commit, and the code there has the checksum;
- the code's `tessel.toml` gives the same name, version and libraries;
- the code compiles, and the libraries it uses are published.

Then it's reviewed and merged, and `tessel add` finds it.

## Names

A library's name is how programs import it: lowercase letters, digits and
`_`, starting with a letter, at most 40 characters. The first published
version claims the name for its repository. Names that impersonate
another project, or are held without a real library, may be removed.
