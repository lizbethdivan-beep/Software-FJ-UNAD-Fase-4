SOFTWARE FJ — UNAD PROGRAMMING 213023 — PHASE 4
================================================

FILES
- phase4_software_fj.py : Python source code and Tkinter graphical interface
- README_Software_FJ.txt: Setup and operation instructions
- simulation_results.txt: Results from the 16 simulated operations

REQUIREMENTS
- Python 3.10+ including Tkinter (standard library)
- Visual Studio Code (recommended)
- No database or third-party Python packages

HOW TO RUN
1. Open the folder containing this file using VS Code: File > Open Folder.
2. Open phase4_software_fj.py.
3. Run the file using "Run Python File" or the command:
       python phase4_software_fj.py
4. Navigate the tabs: Clients, Services, Reservations, Activity & Tests.
5. On Activity & Tests, click RUN 16 SIMULATED OPERATIONS.

RUN HEADLESS DEMO
       python phase4_software_fj.py --demo

DEFAULT DEMONSTRATION RECORDS
Clients: CL-001 and CL-002
Services: SV-101 (meeting room), SV-102 (equipment), SV-103 (consulting)
Reservation inputs can start with CL-001, SV-101, 2 hours, tax=0, discount=0.

EXCEPTION HANDLING EVIDENCE
- Custom exception hierarchy: BusinessError, ValidationError, DuplicateClientError,
  ClientNotFoundError, ServiceUnavailableError, ReservationError.
- try/except/else/finally in the simulation and GUI handlers.
- `raise ... from exc` for explicit exception chaining.
- Each simulation operation is independent; a failed operation is logged and
  later operations continue.
- A log file (software_fj_events.log) is created in the same folder.

DESIGN NOTES
- Encapsulation: Client fields and property validation.
- Abstraction: Entity and Service abstract base classes.
- Inheritance: three specialized Service subclasses.
- Polymorphism: service-specific validation and calculation.
- Overload-like optional parameters: taxes and discounts in calculate_cost.
- Storage: in-memory lists, no database. File writes used only for logs.

DELIVERY PROCESS
1. Test the program locally and capture evidence screenshots.
2. Create a GitHub repository and upload the source and README.
3. Share the GitHub URL in the course forum.
4. Submit the required PDF: cover page, introduction, repository URL,
   conclusions, and APA references.

This is a working starting implementation. Complete local GUI validation and
verify repository access before academic submission.
