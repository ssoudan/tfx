# Copyright 2020 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Data types util shared for orchestration."""
from typing import Dict, Iterable, List, Mapping, Optional, Union, Type, Any

from tfx import types
from tfx.proto.orchestration import pipeline_pb2
from tfx.types import artifact_utils
from tfx.utils import json_utils
from tfx.utils import proto_utils

from ml_metadata.proto import metadata_store_pb2
from ml_metadata.proto import metadata_store_service_pb2

from google.protobuf import message


def build_artifact_dict(
    proto_dict: Mapping[str, metadata_store_service_pb2.ArtifactStructList]
) -> Dict[str, List[types.Artifact]]:
  """Converts input/output artifact dict."""
  result = {}
  for k, v in proto_dict.items():
    result[k] = []
    for artifact_struct in v.elements:
      if not artifact_struct.HasField('artifact'):
        raise RuntimeError('Only support artifact oneof field')
      artifact_and_type = artifact_struct.artifact
      result[k].append(
          artifact_utils.deserialize_artifact(artifact_and_type.type,
                                              artifact_and_type.artifact))
  return result


def build_artifact_struct_dict(
    artifact_dict: Mapping[str, Iterable[types.Artifact]]
) -> Dict[str, metadata_store_service_pb2.ArtifactStructList]:
  """Converts input/output artifact dict."""
  result = {}
  if not artifact_dict:
    return result
  for k, v in artifact_dict.items():
    artifact_list = metadata_store_service_pb2.ArtifactStructList()
    for artifact in v:
      artifact_struct = metadata_store_service_pb2.ArtifactStruct(
          artifact=metadata_store_service_pb2.ArtifactAndType(
              artifact=artifact.mlmd_artifact, type=artifact.artifact_type))
      artifact_list.elements.append(artifact_struct)
    result[k] = artifact_list
  return result


def build_value_dict(
    metadata_value_dict: Mapping[str, metadata_store_pb2.Value]
) -> Dict[str, types.Property]:
  """Converts MLMD value dict into plain value dict."""
  result = {}
  for k, v in metadata_value_dict.items():
    result[k] = getattr(v, v.WhichOneof('value'))
  return result


def build_metadata_value_dict(
    value_dict: Mapping[str, types.Property]
) -> Dict[str, metadata_store_pb2.Value]:
  """Converts plain value dict into MLMD value dict."""
  result = {}
  if not value_dict:
    return result
  for k, v in value_dict.items():
    value = metadata_store_pb2.Value()
    if isinstance(v, str):
      value.string_value = v
    elif isinstance(v, int):
      value.int_value = v
    elif isinstance(v, float):
      value.double_value = v
    else:
      raise RuntimeError('Unsupported type {} for key {}'.format(type(v), k))
    result[k] = value
  return result


def build_parsed_value_dict(
    value_dict: Mapping[str, metadata_store_pb2.Value],
    schema_dict: Mapping[str, pipeline_pb2.Value.Schema]) -> Dict[str, Any]:
  """Converts MLMD value into parsed (non-)primitive value dict."""

  def parse_value(
      value: str, value_type: pipeline_pb2.Value.Schema.ValueType
  ) -> Union[message.Message, bool]:
    if value_type.HasField('proto_metadata'):
      return proto_utils.deserialize_proto_message(
          value, value_type.proto_metadata.message_type,
          value_type.proto_metadata.file_descriptors)
    elif value_type.boolean_type:
      return json_utils.loads(value)

  result = {}
  if not value_dict:
    return result
  for k, v in value_dict.items():
    if v.HasField('string_value') and k in schema_dict:
      schema = schema_dict[k]
      value = v.string_value

      if schema.container_type == pipeline_pb2.Value.Schema.ContainerType.LIST:
        list_value = json_utils.loads(value)
        value = [parse_value(val, schema.value_type) for val in list_value]
      else:
        value = parse_value(value, schema.value_type)
    else:
      value = getattr(v, v.WhichOneof('value'))
    result[k] = value
  return result


def get_metadata_value_type(
    value: Union[pipeline_pb2.Value, types.Property]
) -> metadata_store_pb2.PropertyType:
  """Gets the metadata property type of a property value from a value.

  Args:
    value: The property value represented by pipeline_pb2.Value or a primitive
      property value type.

  Returns:
    A metadata_store_pb2.PropertyType.

  Raises:
    RuntimeError: If property value is still in RuntimeParameter form
    ValueError: The value type is not supported.
  """
  if isinstance(value, int):
    return metadata_store_pb2.INT
  elif isinstance(value, float):
    return metadata_store_pb2.DOUBLE
  elif isinstance(value, str):
    return metadata_store_pb2.STRING
  elif isinstance(value, pipeline_pb2.Value):
    which = value.WhichOneof('value')
    if which != 'field_value':
      raise RuntimeError('Expecting field_value but got %s.' % value)

    value_type = value.field_value.WhichOneof('value')
    if value_type == 'int_value':
      return metadata_store_pb2.INT
    elif value_type == 'double_value':
      return metadata_store_pb2.DOUBLE
    elif value_type == 'string_value':
      return metadata_store_pb2.STRING
    else:
      raise ValueError('Unexpected value type %s' % value_type)
  else:
    raise ValueError('Unexpected value type %s' % type(value))


def get_value(tfx_value: pipeline_pb2.Value) -> types.Property:
  """Gets the primitive type value of a pipeline_pb2.Value instance.

  Args:
    tfx_value: A pipeline_pb2.Value message.

  Returns:
    The primitive type value of the tfx value.

  Raises:
    RuntimeError: when the value is still in RuntimeParameter form.
  """
  which = tfx_value.WhichOneof('value')
  if which != 'field_value':
    raise RuntimeError('Expecting field_value but got %s.' % tfx_value)

  return getattr(tfx_value.field_value,
                 tfx_value.field_value.WhichOneof('value'))


def get_metadata_value(
    value: metadata_store_pb2.Value) -> Optional[types.Property]:
  """Gets the primitive type value of a metadata_store_pb2.Value instance.

  Args:
    value: A metadata_store_pb2.Value message.

  Returns:
    The primitive type value of metadata_store_pb2.Value instance if set, `None`
    otherwise.
  """
  which = value.WhichOneof('value')
  return None if which is None else getattr(value, which)


def set_metadata_value(
    metadata_value: metadata_store_pb2.Value,
    value: Union[pipeline_pb2.Value,
                 types.Property]) -> metadata_store_pb2.Value:
  """Sets metadata property based on tfx value.

  Args:
    metadata_value: A metadata_store_pb2.Value message to be set.
    value: The value of the property in pipeline_pb2.Value form.

  Returns:
    A Value proto filled with the provided value.

  Raises:
    ValueError: If value type is not supported or is still RuntimeParameter.
  """
  # bool is a subclass of int...
  if isinstance(value, int) and not isinstance(value, bool):
    metadata_value.int_value = value
  elif isinstance(value, float):
    metadata_value.double_value = value
  elif isinstance(value, str):
    metadata_value.string_value = value
  elif isinstance(value, pipeline_pb2.Value):
    which = value.WhichOneof('value')
    if which != 'field_value':
      raise ValueError('Expecting field_value but got %s.' % value)

    metadata_value.CopyFrom(value.field_value)
  else:
    raise ValueError('Unexpected type %s' % type(value))
  return metadata_value


def set_parameter_value(
    parameter_value: pipeline_pb2.Value,
    value: types.Property,
    property_type: Optional[Type] = None  # pylint: disable=g-bare-generic
) -> pipeline_pb2.Value:
  """Sets field value and schema based on tfx value.

  Args:
    parameter_value: A pipeline_pb2.Value message to be set.
    value: The value of the property.
    property_type: Optional. The type of the property.

  Returns:
    A pipeline_pb2.Value proto with field_value and schema filled based on input
    property.

  Raises:
    ValueError: If value type is not supported.
  """
  if isinstance(value, int) and not isinstance(value, bool):
    parameter_value.field_value.int_value = value
  elif isinstance(value, float):
    parameter_value.field_value.double_value = value
  elif isinstance(value, str):
    parameter_value.field_value.string_value = value

    def set_value_type(value_type: Type, schema: pipeline_pb2.Value.Schema):  # pylint: disable=g-bare-generic
      if issubclass(value_type, message.Message):
        proto_metadata = schema.value_type.proto_metadata
        proto_metadata.message_type = value_type.DESCRIPTOR.full_name
        proto_utils.build_file_descriptor_set(value_type,
                                              proto_metadata.file_descriptors)
      elif value_type == bool:
        schema.value_type.boolean_type = True

    # Non-primitive types may be serialized. Check property_type to recover its
    # type information.
    if not property_type:
      pass
    elif property_type.__class__.__name__ in ('_GenericAlias', 'GenericMeta'):
      if property_type.__origin__ in [List, list]:
        parameter_value.schema.container_type = (
            pipeline_pb2.Value.Schema.ContainerType.LIST)
        list_value_type = property_type.__args__[0]
        set_value_type(list_value_type, parameter_value.schema)
      else:
        raise ValueError('Serialized string has unexpected type %s' %
                         property_type)
    elif property_type == bool or issubclass(property_type, message.Message):
      set_value_type(property_type, parameter_value.schema)
    else:
      raise ValueError('Serialized string has unexpected type %s' %
                       property_type)
  else:
    raise ValueError('Unexpected type %s' % type(value))

  return parameter_value
