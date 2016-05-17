The YAML source files for the API documentation are written according to the
Swagger specification [1]. Swagger API specifications can be written in JSON
or YAML. For convenience, ease of editing, and the capability of having in-line
comments, the API specifications in this folder are written in YAML.

To aid in the editing Swagger specifications, there is an online Swagger
editor [2] which instantly generates HTML documentation so you can see the
results of your changes.

To output HTML versions of these docs from the command line, use
`tox -e api-ref`. Generated artifacts will be placed in the `api-ref/build/`
directory. Note that `tox -e api-ref` requires that you install `npm` [3].

References:

[1] - http://swagger.io/specification/
[2] - http://editor.swagger.io/
[3] - https://docs.npmjs.com/getting-started/installing-node
