#!/usr/bin/env bash
# This script performs two separate operations:
# * It creates the release commit and tag
# * It creates Gitlab release from Gitlab CI
set -eu
cd "$(dirname "$0")"

# This should be set to the appropriate project name.
project_name="pySHV"

fail() {
	echo "$@" >&2
	exit 1
}

in_ci() {
	[[ "${GITLAB_CI:-}" == "true" ]]
}

is_semver() {
	[[ "$1" =~ ^((0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))(-((0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?(\+([0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*))?$ ]]
}

releases() {
	sed -nE 's/^## \[([^]]+)\].*/\1/p' CHANGELOG.md
}

# Get the latest changelog.
latest_changelog() {
	gawk '
		BEGIN { flag = 0; }
		/^## / && !flag { flag = 1; next; }
		/^## / && flag { exit; }
		flag { print; }
	' CHANGELOG.md
}

################################################################################

if ! in_ci; then

	changelog="$(latest_changelog | sed -E 's|^##[#]+ ||;s|^- |* |')"
	if [[ -z "$changelog" ]] || [[ "$(releases | head -1)" != "Unreleased" ]]; then
		fail "There is no unreleased changelog!"
	fi

	prev="$(releases | sed -n 2p)"
	while true; do
		read -rp "New release (previous: $prev): " version
		if ! is_semver "$version"; then
			echo "Version has to be valid semantic version!"
			continue
		fi
		if git rev-parse "v${version}" >/dev/null 2>&1; then
			echo "This version already exists."
			continue
		fi
		break
	done

	gawk -i inplace -v prev="$prev" -v version="$version" '
		/^## \[Unreleased\]/ {
			print "## [" version "] - " strftime("%Y-%m-%d")
			next
		}
		/^\[unreleased\]: / {
			url = $2; sub("v" prev, "v" version, url)
			print "[unreleased]: " url
			url = $2; sub(/HEAD/, "v" version, url)
			print "[" version "]: " url
			next
		}
		{print}
	' CHANGELOG.md
	if ! grep -F "[unreleased]: " CHANGELOG.md; then
		url=$(sed -n '0,/^source = "/ s|^source = "\([^"]*\)"$|\1|p' pyproject.toml)
		{
			echo && echo
			echo "[unreleased]: $url/compare/v$version..HEAD"
			echo "[$version]: $url/-/tags/v$version"
		} >>CHANGELOG.md
	fi
	[[ "$(releases | head -1)" == "$version" ]] ||
		fail "Failed to set version in CHANGELOG.md"
	sed -i "0,/^version = / s/^version = .*/version = \"${version}\"/" pyproject.toml
	grep -F "version = \"${version}\"" pyproject.toml ||
		fail "Failed to set version in pyproject.toml"
	git commit -ve -m "$project_name version $version" -m "$changelog" CHANGELOG.md pyproject.toml

	while ! gitlint; do
		read -rp "Invalid commit message. Edit again? (Yes/no/force) " response
		case "${response,,}" in
		"" | y | yes)
			git commit --amend
			;;
		n | no)
			git reset --merge HEAD^
			exit 1
			;;
		f | force)
			break
			;;
		esac
	done

	{ python3 -m build && twine check dist/*; } || {
		git reset --merge HEAD^
		fail "Invalid pypi release"
	}

	git tag -s "v${version}" -m "$(git log --format=%B -n 1 HEAD)"

	sed -i "/^## \[${version//./\\.}\] - $(date +%Y-%m-)/ i ## [Unreleased]\n\n" CHANGELOG.md
	git commit -F- CHANGELOG.md <<-EOF
		Preparations for the next development

		This adds unreleased section to the changelog to ensure that future
		changes won't be interpreted as part release by readers.
	EOF

else

	[[ "$CI_COMMIT_TAG" =~ ^v ]] ||
		fail "This is not a release tag: $CI_COMMIT_TAG"
	version="${CI_COMMIT_TAG#v}"
	is_semver "$version" ||
		fail "Version has to be valid semantic version!"
	[[ "$(releases | head -1)" == "$version" ]] ||
		fail "The version $version isn't the latest release in CHANGELOG.md "

	changelog="$(latest_changelog)"
	[[ -n "$changelog" ]] ||
		fail "Changelog is empty!"

	release-cli create \
		--name "Release $version" \
		--tag-name "$CI_COMMIT_TAG" \
		--description "$changelog"
fi
