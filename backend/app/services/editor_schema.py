"""Owned-asset, output-time editing state shared with the browser renderer."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class CropBox(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=.02, le=1)
    height: float = Field(ge=.02, le=1)

    @model_validator(mode="after")
    def inside(self):
        if self.x + self.width > 1.001 or self.y + self.height > 1.001:
            raise ValueError("Crop rectangle must fit the original source")
        return self


class EditorLayer(Contract):
    id:str=Field(pattern=r'^[a-zA-Z0-9-]{1,64}$')
    kind:Literal['text','image','video','audio']
    name:str=Field(max_length=100)
    start:float=Field(ge=0)
    end:float=Field(gt=0)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)
    width:float=Field(ge=.01,le=1)
    height:float=Field(ge=.01,le=1)
    rotation:float=Field(ge=-180,le=180)
    opacity:float=Field(ge=0,le=1)
    visible:bool
    locked:bool
    text:str=Field(max_length=2000)
    asset_id:str|None=Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,64}$')
    font_size:float=Field(ge=12,le=200)
    font_family:Literal['Noto Sans','serif','monospace']
    font_weight:int=Field(ge=100,le=900)
    color:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    background:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    outline_color:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    outline_width:float=Field(ge=0,le=12)
    shadow:bool
    align:Literal['left','center','right']
    animation:Literal['none','fade','pop','slide']
    volume:float=Field(ge=0,le=2)
    fade_in:float=Field(ge=0,le=5)
    fade_out:float=Field(ge=0,le=5)
    trim_start:float=Field(ge=0,le=7200)
    duck:bool

class EditorCaption(Contract):
    font_family:Literal['Noto Sans','serif','monospace']='Noto Sans'
    align:Literal['left','center','right']='center'
    shadow:bool=True
    preset:str=Field(max_length=80)
    size:float=Field(ge=30,le=120)
    color:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    highlight:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    outline:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    outline_width:float=Field(ge=0,le=12)
    background:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
    y:float=Field(ge=.05,le=.95)
    opacity:float=Field(ge=0,le=1)
    rotation:float=Field(ge=-180,le=180)
    letter_spacing:float=Field(ge=-3,le=15)
    line_height:float=Field(ge=.8,le=2)
    weight:int=Field(ge=100,le=900)
    uppercase:bool
    animation:Literal['none','fade','pop','karaoke']

class EditorState(Contract):
    source_rotation:float=Field(default=0,ge=-180,le=180)
    source_scale:float=Field(default=1,ge=.5,le=2)
    source_x:float=Field(default=0,ge=-.5,le=.5)
    source_y:float=Field(default=0,ge=-.5,le=.5)
    brightness:float=Field(default=1,ge=.2,le=2)
    contrast:float=Field(default=1,ge=.2,le=2)
    saturation:float=Field(default=1,ge=0,le=3)
    blur:float=Field(default=0,ge=0,le=30)
    schema_version:Literal[1]
    layers:list[EditorLayer]=Field(max_length=60)
    caption:EditorCaption
    source_volume:float=Field(ge=0,le=2)
    background:str=Field(pattern=r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')

    def check_duration(self,duration):
        if len({layer.id for layer in self.layers})!=len(self.layers):raise ValueError('Duplicate editor layer IDs')
        for layer in self.layers:
            if layer.end<=layer.start or layer.end>duration+.001:raise ValueError('Editor layers must fit the output timeline')
            if layer.kind!='text' and not layer.asset_id:raise ValueError('Media layer requires an owned asset')
        return self
