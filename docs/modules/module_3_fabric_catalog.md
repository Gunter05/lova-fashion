# Module Documentation — Fabric Catalog

## 1. Module Overview

**Module name:** Fabric Catalog

**Main objective:**
Manage the reference catalog of available fabrics (categories and specific references) used
to make custom-fit garments.

**What it enables:**
- Browse and manage fabric categories (Wax, Jersey, Denim, etc.)
- Browse and manage specific fabric references within each category
- Provide other modules with a fabric's technical properties, especially its elasticity rate

## 2. Position in the System

The Fabric Catalog module communicates with:
- Ease Margin Calculation Engine
- Compatibility Verification Engine
- Final Result Generation / Report

**Dependencies:** none. It is a standalone reference-data module — it does not depend on any
other module to function.

## 3. Actors Involved

**Human users:**
- Client (browses and selects a fabric)
- Catalog manager / Administrator (adds, edits, or removes a fabric)

**Automated systems:**
- Ease Margin Calculation Engine (consumes the elasticity rate)
- Compatibility Verification Engine (consumes the category and rigidity level)

## 4. Functional Description

The module enables:
- browsing the list of available fabrics, grouped by category
- viewing a fabric's detail (elasticity, weight, composition, price)
- adding a new fabric category
- adding, editing, or removing a fabric reference
- providing the elasticity rate and rigidity level of a given fabric to the modules that need it

**Expected result:** the client chooses a fabric with full knowledge of its properties, and
the calculation modules have the data they need to adjust the pattern.

## 5. Glossary

**Fabric:**
A specific textile reference available in the catalog (e.g. Wax Vlisco ref. 1234).

**Fabric category:**
A family of fabrics sharing similar properties (e.g. Wax, Jersey, Denim).

**Elasticity rate:**
A measure of a fabric's ability to stretch, used to calculate ease margins.

**Ease margin:**
Extra space added to measurements to ensure the garment's comfort (calculated by another
module from the data provided by this catalog).

## 6. Use Cases

### Use case: Select a fabric for a garment

**Goal:** obtain the technical properties of a chosen fabric.

**Trigger:** the client selects a fabric in the order interface.

**Steps:**
1. The client browses the list of fabrics by category.
2. The client selects a specific reference.
3. The system displays its properties (elasticity, weight, composition, price).
4. The client confirms their choice.

**Result:** the chosen fabric is passed to the ease margin and compatibility modules.

### Use case: Add a fabric to the catalog

**Goal:** enrich the catalog with a new reference.

**Trigger:** a manager wants to add a new fabric.

**Steps:**
1. The manager selects an existing category (or creates a new one).
2. They enter the fabric's properties (name, elasticity, weight, composition, price).
3. The system saves the new reference.

**Result:** the fabric is available for clients to select.

## 7. Business Rules

- A fabric must belong to exactly one category.
- The elasticity rate must be between 0% and 100%.
- A fabric marked unavailable cannot be selected by a client.
- A fabric's unit price must be positive.

## 8. Module States

Possible states of a fabric in the catalog:

- `available` -> visible and selectable by clients
- `unavailable` -> temporarily withdrawn from sale, not selectable
- `archived` -> permanently removed from the catalog, kept for history

## 9. Interactions With Other Modules

**Input:**
`fabric.selected` — emitted by the interface when the client chooses a fabric

**Triggered action:**
Retrieval of the fabric's technical properties (elasticity, rigidity)

**Output:**
`fabric.properties_provided` — sent to the Ease Margin Calculation Engine and the
Compatibility Verification Engine

## 10. Error Handling

**Error:** Fabric not found (invalid reference)
**Response:** display an error message and return to the list of available fabrics.

**Error:** Attempt to create a fabric without an associated category
**Response:** block the creation until a category is selected.

**Error:** Selection of a fabric marked unavailable
**Response:** prevent the selection and suggest similar available fabrics.
