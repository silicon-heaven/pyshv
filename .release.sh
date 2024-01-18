#!/usr/bin/env bash
set -eu

version="${CI_COMMIT_TAG#v}"
if ! grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' <<<"$version"; then
	echo "Tag has to be valid version number such as v1.0.0!" >&2
	exit 1
fi

if [[ "$(cat ./*/version)" != "$version" ]]; then
	echo "Version file does not contain the correct version!" >&2
	exit 1
fi

# Changelog should contain as a first section this release as this is the
# latest release.
changelog="$(awk -v "version=$version" '
		BEGIN {
			flag = 0
		}
		/^## / {
			if ( $0 !~ "^## \\[" version "\\]" ) {
				exit
			}
			flag = 1
			next
		}
		/^## \[/ && flag {
			exit
		}
		flag {
			print
		}
	' CHANGELOG.md)"
if [ -z "$changelog" ]; then
	echo "Changelog is empty." \
		"Have you updated the version? Is this the latest version?" >&2
	exit 1
fi

release-cli create \
	--name "Release $version" \
	--tag-name "$CI_COMMIT_TAG" \
	--description "$changelog"
