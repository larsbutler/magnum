#!/bin/bash -xe
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


function swagger_bootprint_html {

    source_dir="api-ref/source"
    build_dir="api-ref/build"

    # ensure the build dir exists
    mkdir -p $build_dir

    # Convert the Swagger YAML files to JSON
    for i in ${source_dir}/*.yaml
        do
        # root of file name, without extension
        source_file_basename=$(basename "$i")
        root_file_name=${source_file_basename%.*}
        python tools/swagger_yaml_to_json.py $i ${build_dir}/${root_file_name}.json
    done

    # Generate HTML plus CSS for each Swagger JSON file
    for i in $build_dir/*.json
        do
        source_file_name=${i##*/}
        full_output_dir=${build_dir}/${source_file_name%.*}
        bootprint openapi $i $full_output_dir
    done
}

swagger_bootprint_html
