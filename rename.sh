#!/usr/bin/env bash
set -eu

check_name()
{
	# https://packaging.python.org/en/latest/specifications/name-normalization/
	if ! echo $1 | grep -Ei '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'
	then
		echo "Name not allowed."
		echo "Please, keep it regexp '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$',"
		echo "where case does not matter."
		exit 1
	fi
}

normalize_name()
{
	# https://packaging.python.org/en/latest/specifications/name-normalization/
	echo "$1" | sed -Ee 's/[-_.]+/-/g' | tr '[:upper:]' '[:lower:]'
}

read -p "New project name: " project_name
project_name=$(check_name "$project_name")
read -p "One line project description: " project_oneliner
read -p "New package name: " package_name
package_name=$(normalize_name $(check_name "$package_name"))
# $package_name is also used as the name of the executable

project_url=$(git remote get-url origin)
project_url=${project_url%.git}
project_url=${project_url//://}
project_url=${project_url//git@/https://}

# Update project info
#
sed -i "s|Project Template Python|$project_oneliner|g" \
	flake.nix pyproject.toml README.rst docs/conf.py

sed -i "2s|=======================|${project_oneliner//?/=}|g" \
	README.rst

sed -i "s|https://gitlab.elektroline.cz/emb/template/python|$project_url|g" \
	pyproject.toml README.rst

sed -i "s|project-template-python|${project_name}|g" \
	pyproject.toml release.sh

# Update package name
#
sed -i "s|template_package_name|${package_name}|g" \
	docs/api.rst pyproject.toml flake.nix \
	tests/test_* \
	template_package_name/__init__.py
mv template_package_name/ ${package_name}
