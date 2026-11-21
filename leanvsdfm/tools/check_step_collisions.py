#!/usr/bin/env python3
"""Check for shared solid volume between component instances in a KiCad STEP assembly."""

import argparse
from itertools import combinations
import sys

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.XCAFDoc import XCAFDoc_DocumentTool

MIN_REPORTABLE_VOLUME_MM3 = 1e-9


def label_name(label):
    attribute = TDataStd_Name()
    if label.FindAttribute(attribute.GetID_s(), attribute):
        return attribute.Get().ToExtString()
    return ""


def read_components(path):
    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    reader = STEPCAFControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone or not reader.Transfer(document):
        raise ValueError("could not import the STEP assembly")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise ValueError("expected one top-level KiCad assembly")
    instances = TDF_LabelSequence()
    shape_tool.GetComponents_s(roots.Value(1), instances)
    components = {}
    boards = 0
    for index in range(1, instances.Length() + 1):
        instance = instances.Value(index)
        product = TDF_Label()
        if not shape_tool.GetReferredShape_s(instance, product):
            raise ValueError(f"missing product for assembly instance {index}")
        if label_name(product).endswith(" PCB"):
            boards += 1
            continue
        ref = label_name(instance)
        if not ref or ref in components:
            raise ValueError(f"missing or duplicate component reference at instance {index}")
        shape = shape_tool.GetShape_s(instance)
        if (shape.IsNull() or not TopExp_Explorer(shape, TopAbs_SOLID).More()
                or TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID).More()):
            raise ValueError(f"{ref} does not consist of solid geometry")
        components[ref] = shape
    if boards != 1:
        raise ValueError("expected one PCB substrate in the STEP assembly")
    return components


def bounding_box(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box


def common_volume(first, second):
    intersection = BRepAlgoAPI_Common(first, second)
    if not intersection.IsDone():
        raise ValueError("OpenCascade did not complete the intersection")
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(intersection.Shape(), properties, True)
    return properties.Mass()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", help="KiCad STEP assembly")
    parser.add_argument("--expected-components", required=True, type=int, help="number of modeled components")
    args = parser.parse_args()
    if args.expected_components < 2:
        parser.error("at least two expected components are required")

    try:
        components = read_components(args.step)
        if len(components) != args.expected_components:
            raise ValueError(f"expected {args.expected_components} components, found {len(components)}")
        boxes = {ref: bounding_box(shape) for ref, shape in components.items()}
        collisions = 0
        for first, second in combinations(components, 2):
            if boxes[first].IsOut(boxes[second]):
                continue
            volume = common_volume(components[first], components[second])
            if volume > MIN_REPORTABLE_VOLUME_MM3:
                print(f"{first} vs {second}: {volume:.6g} mm³ of shared solid volume")
                collisions += 1
    except (RuntimeError, ValueError) as exc:
        print(f"STEP collision check could not complete: {exc}", file=sys.stderr)
        return 2

    print(f"{len(components)} STEP components, {collisions} colliding pairs.")
    return 3 if collisions else 0


if __name__ == "__main__":
    sys.exit(main())
