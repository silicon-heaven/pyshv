#!/usr/bin/env bash
# Script that builds documentations for different Git references and stitches
# them together so they can be switched.
set -eu
out="$1"
shift

git fetch # To get all references

# Collect versions
versions=("$CI_DEFAULT_BRANCH")
while read -r ref; do
	versions+=("${ref#refs/tags/}")
done < <(git for-each-ref --format "%(refname)" 'refs/tags/v*' | sort -Vr)

# Build documentation for every version and deploy it to the output directory
for ref in "${versions[@]}"; do
	echo -e "\e[0Ksection_start:$(date +%s):${ref}[collapsed=true]\r\e[0K$*"
	if res="$(
		nix build --no-link --print-out-paths \
			".?submodules=1&ref=${ref}#default.doc"
	)"; then
		mkdir -p "$out"
		rm -rf "${out:?}/${ref}"
		cp -r --no-preserve=mode "$res"/share/doc/*/html "$out/$ref"
		{
			echo "{"
			echo "  \"current\": \"${ref}\"",
			echo "  \"versions\": ["
			first="yes"
			for rref in "${versions[@]}"; do
				if [[ "$ref" != "$rref" ]]; then
					[[ -n "$first" ]] || echo ","
					first=""
					echo -n "    \"${rref}\""
				fi
			done
			echo
			echo "  ]"
			echo "}"
		} >"$out/$ref/versions.json"
	fi
	echo -e "\e[0Ksection_end:$(date +%s):$ref\r\e[0K"
done

# Add redirecting index to the root
cat >"$out/index.html" <<EOF
<!DOCTYPE html>
<html>
	<head>
		<title>Redirecting to $CI_DEFAULT_BRANCH branch</title>
		<meta charset="utf-8">
		<meta http-equiv="refresh" content="0; url=./$CI_DEFAULT_BRANCH/index.html">
		<link href="./$CI_DEFAULT_BRANCH/index.html">
	</head>
</html>
EOF
