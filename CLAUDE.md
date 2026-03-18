# CLAUDE.md — SharpNTCIP Repository Guide

## Project Overview

**SharpNTCIP** is a C# .NET class library implementing the **NTCIP (National Transportation Communications for ITS Protocol)** standard. It provides data models and utilities for interacting with:

- **DMS (Dynamic Message Signs)** — Variable message signs on roadways (NTCIP 1203:1997)
- **TSS (Traffic Sensor Systems)** — Inductive loop detectors and machine vision sensors (NTCIP 8004)

The library is licensed under **GNU LGPL v3** and targets .NET Framework 4.0.

The actual source code lives inside `SharpNTCIP-master.zip`. There is no build system configured in this repository outside that archive.

---

## Repository Layout

```
/home/user/dms/
└── SharpNTCIP-master.zip     # Full project source
```

### Inside the zip (`SharpNTCIP-master/`):

```
SharpNTCIP-master/
├── Attributes/                  # Custom NTCIP metadata attributes
│   ├── NtcipAccessAttribute.cs  # Marks property read/write/none access level
│   ├── NtcipMandatoryAttribute.cs # Marks if property is mandatory per standard
│   └── NtcipOidAttribute.cs     # Maps property to NTCIP OID string
├── DMS/                         # Dynamic Message Sign domain
│   ├── IDms.cs                  # Root DMS device interface
│   ├── IDmsSignConfig.cs        # Physical sign configuration
│   ├── IDmsMessage.cs           # Message storage objects
│   ├── IDmsMessageEntry.cs      # Individual message definition
│   ├── IMultiConfig.cs          # MULTI tag formatting config
│   ├── ISignControl.cs          # Display/activation control
│   ├── IIllumination.cs         # Brightness/lighting control
│   ├── IFontDefinition.cs       # Available fonts
│   ├── IDmsStatus.cs            # Status and error reporting
│   ├── MultiUtility.cs          # MULTI string parser (MultiString class)
│   ├── MessageIDCode.cs         # Message ID structure
│   ├── MessageActivationCode.cs # Message activation structure
│   ├── GeneralErrorException.cs # NTCIP error exception
│   ├── FontTable.cs             # Font table implementation
│   ├── DmsMessageTable.cs       # Message table implementation
│   └── ...                      # Additional table/entry implementations
├── TSS/                         # Traffic Sensor System domain
│   ├── ITSSDevice.cs            # Root TSS device interface
│   ├── ITSSSystemSetup.cs       # System configuration
│   ├── ITSSControl.cs           # Control operations
│   ├── ITSSInductiveLoop.cs     # Inductive loop sensor data
│   ├── ITSSMachineVision.cs     # Machine vision sensor data
│   └── DataCollection.cs        # Data collection management
├── Test/
│   ├── Tests/Test_Multi.cs      # MSTest unit tests for MultiString
│   └── Runner/Program.cs        # Console sample demonstrating MultiString
├── Properties/AssemblyInfo.cs   # Assembly version/metadata
├── IGlobalConfiguration.cs      # Base interface for all NTCIP devices
├── IAuxiliaryIo.cs              # Auxiliary I/O interface
├── Helper.cs                    # Utility functions (OID lookup, enum parsing)
├── Table.cs                     # Generic abstract table base class
├── ReadOnlyTable.cs             # Read-only table variant
├── ModuleTableEntry.cs          # Module identification entry
├── SpeedSensorSample.cs         # Speed sensor sample data
├── SharpNTCIP.csproj            # Main library project file
├── SharpNTCIP.sln               # Visual Studio solution
├── README.md                    # Minimal placeholder readme
└── LICENSE                      # GNU LGPL v3
```

---

## Technology Stack

| Component | Details |
|-----------|---------|
| Language | C# |
| Target Framework | .NET Framework 4.0 (library), 4.5 (tests) |
| Build System | MSBuild via Visual Studio 2012+ |
| Test Framework | MSTest (`Microsoft.VisualStudio.TestTools.UnitTestFramework`) |
| External Dependencies | None — only .NET base class libraries |
| Output | `SharpNTCIP_NuGet/lib/net40/SharpNTCIP.dll` |

---

## Architecture and Key Patterns

### 1. Attribute-Based OID Mapping

Properties on NTCIP interfaces are decorated with custom attributes that encode the SNMP OID, access level, and mandatory status from the standard:

```csharp
[NtcipOid("1.3.6.1.4.1.1206.4.2.3.1"),
 NtcipAccess(NtcipAccessAttribute.Access.read),
 NtcipMandatory(true)]
IDmsSignConfig dmsSignCfg { get; }
```

Use `Helper.GetOid(typeof(IDms), "dmsSignCfg")` to retrieve the OID string at runtime via reflection.

### 2. Interface Hierarchy

All device interfaces extend `IGlobalConfiguration`:

```
IGlobalConfiguration
└── IDms (Dynamic Message Signs)
└── ITSSDevice (Traffic Sensor Systems)
```

Consumers implement these interfaces to wrap real SNMP/NTCIP device communication.

### 3. Table Pattern

`Table<K, V>` is an abstract wrapper around `IDictionary<K, V>` for NTCIP table objects. `ReadOnlyTable<K, V>` extends this with read-only enforcement.

### 4. MultiString (MULTI Tag Parser)

`MultiString` in `DMS/MultiUtility.cs` converts between:
- **MULTI string** — `"THIS IS [cb3]A TEST [cb]WITH COLOR CHANGE"`
- **XML document** — `<multi>THIS IS <cb3 />A TEST <cb />WITH COLOR CHANGE</multi>`
- **Plain text** — `"THIS IS A TEST WITH COLOR CHANGE"` (via `ToString()`)

The MULTI format uses `[tagname]` for formatting directives (color, font, spacing, etc.).

### 5. Helper Utilities (`Helper.cs`)

- `Helper.GetOid(Type, string)` — Retrieves NTCIP OID string from interface property via reflection
- `Helper.EnumParse<T>(object)` — Safely casts NTCIP enum values; throws `InvalidCastException` with informative message if value is unknown
- `Helper.formatOid(string, params object[])` — Formats OID strings with integer row/column indices

---

## Building the Project

1. Extract `SharpNTCIP-master.zip`
2. Open `SharpNTCIP.sln` in Visual Studio 2012 or later
3. Build the solution (`Ctrl+Shift+B`)
4. Output: `SharpNTCIP_NuGet/lib/net40/SharpNTCIP.dll`

No NuGet restore is needed — the library has zero third-party dependencies.

---

## Running Tests

**Via Visual Studio:**
- Open Test Explorer and run all tests in `SharpNTCIP.Test.Tests`

**Via MSTest CLI:**
```bash
mstest.exe /testcontainer:SharpNtcipTests.dll
```

**Test Coverage:**
- `Test_Multi.cs` tests the `MultiString` class:
  - `MultiInstantiation()` — round-trip MULTI string
  - `MultiXml()` — MULTI → XML conversion
  - `MultiToString()` — MULTI → plain text stripping tags

---

## Code Conventions

- **PascalCase** for all public types, interfaces, properties, and methods
- **camelCase** for private fields (e.g., `_oid`, `_table`)
- **`I` prefix** on all interfaces (e.g., `IDms`, `ITSSDevice`)
- **XML doc comments** (`<summary>`, `<seealso>`, `<remarks>`) on all public APIs, referencing the NTCIP standard document and section
- **Attribute triples** — every NTCIP interface property must have `[NtcipOid(...)]`, `[NtcipAccess(...)]`, and `[NtcipMandatory(...)]`
- No linter or `.editorconfig` is configured; follow existing style

---

## Key Domain Concepts

### NTCIP OID
A dot-notation string identifying an object in the SNMP MIB tree used by NTCIP devices (e.g., `"1.3.6.1.4.1.1206.4.2.3.1"`). All interface properties map to an OID.

### MULTI Language
A markup language for dynamic message signs. Tags are enclosed in square brackets: `[cb3]` (color background, index 3), `[fo3]` (font, index 3), `[nl]` (new line). See NTCIP 1203 for the full tag set.

### DMS (Dynamic Message Sign)
Electronic roadway signs. The library models:
- Physical configuration (dimensions, pixel size, color capabilities)
- Message storage (permanent messages, changeable messages)
- Sign control (activate message, pixel test, control mode)
- Status and error reporting

### TSS (Traffic Sensor System)
Traffic detection devices (inductive loops, machine vision cameras). Models system setup, sensor zones, data collection, and control.

### Access Levels (`NtcipAccessAttribute.Access`)
- `none` — not directly accessible via SNMP (group/container node)
- `read` — read-only SNMP GET
- `write` — read-write SNMP GET/SET

---

## No CI/CD or Environment Variables

This project has no CI/CD pipeline, no environment variables, and no runtime configuration files. It is a pure .NET library with no deployment concerns.

---

## License

GNU Lesser General Public License v3 (LGPL v3). See `LICENSE` in the archive.
