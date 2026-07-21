# Product Vision

## Context
AWS re:Deploy 2026 — Month 1 (July) — Theme: Fashion

## Problem
Custom tailoring in Cameroon depends on an in-person fitting by a tailor. This application
estimates sewing measurements remotely from two photos (front + side) and the user's height,
then automatically adapts ease margins based on the chosen fabric and checks the
compatibility between fabric, garment pattern, and body shape.

## Target users
- End client: wants a well-fitted garment without visiting a tailor.
- Catalog manager: maintains available fabrics and garment patterns.

## Functional modules
1. Authentication & User Profile
2. Photo Capture & Measurement Estimation (Computer Vision)
3. Fabric Catalog
4. Garment Pattern Catalog
5. Ease Margin Calculation Engine
6. Fabric / Pattern / Body Shape Compatibility Engine
7. Final Result / Report

## Competition constraint
Kiro must be central to building the solution (mandatory for scoring). Each module must have
a Kiro spec (`.kiro/specs/<module>/`) before it is implemented.
