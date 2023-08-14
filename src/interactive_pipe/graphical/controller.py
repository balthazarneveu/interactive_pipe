from typing import List, Optional
from headless.pipeline import HeadlessPipeline
from copy import deepcopy
from abc import abstractmethod
from interactive_pipe.core.control import Control

class PipelineController():
    def __init__(self, pipeline: HeadlessPipeline, controls: dict={}) -> None:
        self.pipeline = pipeline
        self.__all_filters = [filter.name for filter in self.pipeline.filters]
        self.controls = controls
    def __get_filter_index_by_name(self, name:str | int):
        if isinstance(name, int):
            return name
        else:
            assert isinstance(name, str)
            assert name in self.__all_filters
        return self.__all_filters.index(name)
    def add_control(self, filter: int | str , control):
        filter_index = self.__get_filter_index_by_name(filter)
        control_dict = {
            "name": control.name,
            "value_default": control.value_default,
            "filter_index": filter_index,
            "filter_name": self.pipeline.filters[filter_index].name,
            "filter": self.pipeline.filters[filter_index]
        }
        self.controls.append(control_dict)
    def update(self, control_name, value):
        self.controller[c]
        
        

        
