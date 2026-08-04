PYTHON ?= python3

.PHONY: doctor test schema validate host-smoke package-check validate-all example

doctor:
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py doctor

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

schema:
	$(PYTHON) scripts/validate_schemas.py

validate:
	$(PYTHON) scripts/validate.py

host-smoke:
	$(PYTHON) scripts/host_smoke.py

package-check:
	$(PYTHON) scripts/check_package.py

validate-all: schema validate host-smoke package-check
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py self-test

example:
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py compile-image \
		--file examples/premium-haircare-launch/image-job.json
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py compile-video \
		--file examples/premium-haircare-launch/video-job.json
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py validate-project \
		--root examples/premium-haircare-launch
