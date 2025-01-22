#!/usr/bin/env bash
set -eu

readme_head="$(head -1 README.rst)"
read -rp "Full project name [$readme_head]: " project_oneliner
project_oneliner="${project_oneliner:-${readme_head}}"

read -rp "Python project name: " project_name
# https://packaging.python.org/en/latest/specifications/name-normalization/
grep -qEi '^([a-z0-9]|[a-z0-9][a-z0-9._-]*[a-z0-9])$' <<<"$project_name" || {
	echo "Name not allowed." >&2
	echo "Please, keep it regexp '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'," >&2
	echo "where case does not matter." >&2
	exit 1
}

package_project_name="${project_name//[^A-Za-z0-9_]/_}"
read -rp "Python package name [$package_project_name]: " package_name
package_name="${package_name:-${package_project_name}}"
grep -qEi '^[a-z_]\w*$' <<<"$package_name" || {
	echo "Invalid python package name. It must be valid Python identifier." >&2
	exit 1
}
# $package_name is also used as the name of the executable

project_url="$(git remote get-url origin)"
project_url="${project_url%.git}"
project_url="${project_url//://}"
project_url="${project_url//git@/https://}"

# Update project info
#
sed -i "s|Project Template Python|$project_oneliner|g" \
	flake.nix pyproject.toml README.rst docs/conf.py release.sh

sed -i "2s|^=*$|${project_oneliner//?/=}|g" README.rst

sed -i "s|https://gitlab.elektroline.cz/emb/template/python|$project_url|g" \
	pyproject.toml README.rst

sed -i "s|project-template-python|${project_name}|g" \
	pyproject.toml

# Update package name
sed -i "s|template_package_name|${package_name}|g" \
	docs/api.rst pyproject.toml flake.nix \
	tests/test_* \
	template_package_name/__init__.py
mv template_package_name/ "${package_name}"

# Remove this script as it won't work anyway after this
rm -f "${0}"
