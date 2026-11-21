"""Short procedurally generated accents; no third-party sound asset is copied."""
import math,random,struct,wave


def write_cue(kind,path):
    rate=48000;duration=.12 if kind=='click' else .3
    random_source=random.Random(2031);samples=[]
    for i in range(round(rate*duration)):
        t=i/rate;envelope=math.sin(math.pi*t/duration)**2
        signal=math.sin(2*math.pi*1000*t)*math.exp(-45*t) if kind=='click' else random_source.uniform(-1,1)*.35
        samples.append(round(max(-1,min(1,signal*envelope))*32767))
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(struct.pack('<'+'h'*len(samples),*samples))
