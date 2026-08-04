PYTHON ?= python3

.PHONY: doctor test schema validate validate-all example

doctor:
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py doctor

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

schema:
	$(PYTHON) scripts/validate_schemas.py

validate:
	$(PYTHON) scripts/validate.py

validate-all: schema validate
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py self-test

example:
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py compile-image \
		--file examples/premium-haircare-launch/image-job.json
	$(PYTHON) skills/creative-craft/scripts/creative_craft.py compile-video \
		--file examples/premium-haircare-launch/video-job.json
