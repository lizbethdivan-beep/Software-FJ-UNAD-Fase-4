"""Software FJ | Phase 4 UNAD Programming 213023.

Individual simulation of customer, service, and reservation management.
No database: in-memory lists and a local events/errors log only.
Run: python phase4_software_fj.py
Test without a display: python phase4_software_fj.py --demo
"""

from __future__ import annotations

import argparse
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


# --- Logging: event/error history is the only persisted application data. ---
LOG_FILE = Path(__file__).with_name("software_fj_events.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger("software_fj")


# --- Domain-specific exceptions make failures explicit and recoverable. ---
class BusinessError(Exception):
    """Base exception for predictable business-rule failures."""


class ValidationError(BusinessError):
    """An input or operation fails domain validation."""


class DuplicateClientError(BusinessError):
    """An existing client already uses this ID."""


class ClientNotFoundError(BusinessError):
    """The requested client does not exist."""


class ServiceUnavailableError(BusinessError):
    """A requested service is missing or inactive."""


class ReservationError(BusinessError):
    """A reservation violates processing or state rules."""


# --- Shared abstract entity: enforces a common object identity. ---
class Entity(ABC):
    @property
    @abstractmethod
    def identifier(self) -> str:
        """Return the unique identifier for this entity."""


def nonempty(value: str, label: str) -> str:
    """Validate text fields, stripping leading and trailing whitespace."""
    value = str(value).strip()
    if not value:
        raise ValidationError(f"{label} is required.")
    return value


def positive_number(raw: object, label: str, allow_zero: bool = False) -> float:
    """Convert to a finite number with a clear, chained error cause."""
    try:
        value = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"{label} must be a number.") from exc
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        condition = "non-negative" if allow_zero else "greater than zero"
        raise ValidationError(f"{label} must be finite and {condition}.")
    return value


class Client(Entity):
    """Client with encapsulated personal fields and validated updates."""

    def __init__(self, client_id: str, name: str, email: str) -> None:
        self._client_id = nonempty(client_id, "Client ID")
        self._name = nonempty(name, "Client name")
        self.email = email

    @property
    def identifier(self) -> str:
        return self._client_id

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = nonempty(value, "Client name")

    @property
    def email(self) -> str:
        return self._email

    @email.setter
    def email(self, value: str) -> None:
        value = nonempty(value, "Email")
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValidationError("Enter a valid email address.")
        self._email = value

    def describe(self) -> str:
        return f"{self.identifier} | {self.name} | {self.email}"


class Service(Entity, ABC):
    """Abstract service contract for polymorphic cost and validation."""

    kind = "Service"

    def __init__(self, code: str, name: str, hourly_rate: float) -> None:
        self._code = nonempty(code, "Service code")
        self.name = nonempty(name, "Service name")
        self.hourly_rate = positive_number(hourly_rate, "Hourly rate")
        self.available = True

    @property
    def identifier(self) -> str:
        return self._code

    @abstractmethod
    def validate_duration(self, duration: float) -> None:
        """Specialized service rules for permitted duration."""

    def calculate_cost(self, duration: float, tax_rate: float = 0.0,
                       discount_rate: float = 0.0) -> float:
        """Optional tax and discount parameters simulate method overloading."""
        duration = positive_number(duration, "Duration")
        tax_rate = positive_number(tax_rate, "Tax rate", allow_zero=True)
        discount_rate = positive_number(discount_rate, "Discount rate", allow_zero=True)
        if tax_rate > 1 or discount_rate > 1:
            raise ValidationError("Tax and discount rates cannot exceed 100%.")
        self.validate_duration(duration)
        subtotal = self._base_cost(duration)
        return round(subtotal * (1 - discount_rate) * (1 + tax_rate), 2)

    @abstractmethod
    def _base_cost(self, duration: float) -> float:
        """Service-specific pricing behavior."""

    def describe(self) -> str:
        return f"{self.kind} | {self.name} | ${self.hourly_rate:,.2f}/hour"


class RoomReservationService(Service):
    kind = "Meeting Room"

    def validate_duration(self, duration: float) -> None:
        if not 1 <= duration <= 8:
            raise ValidationError("Meeting room bookings must last 1–8 hours.")

    def _base_cost(self, duration: float) -> float:
        return self.hourly_rate * duration


class EquipmentRentalService(Service):
    kind = "Equipment Rental"

    def validate_duration(self, duration: float) -> None:
        if not 1 <= duration <= 72:
            raise ValidationError("Equipment rentals must last 1–72 hours.")

    def _base_cost(self, duration: float) -> float:
        return self.hourly_rate * duration + 15000  # fixed handling fee


class ConsultingService(Service):
    kind = "Consulting"

    def validate_duration(self, duration: float) -> None:
        if not 0.5 <= duration <= 12:
            raise ValidationError("Consulting sessions must last 0.5–12 hours.")

    def _base_cost(self, duration: float) -> float:
        return self.hourly_rate * duration * 1.10  # specialist premium


@dataclass
class Reservation(Entity):
    """Association of one client, one service, duration and lifecycle."""
    reservation_id: str
    client: Client
    service: Service
    duration: float
    total: float
    status: str = "PENDING"

    @property
    def identifier(self) -> str:
        return self.reservation_id

    def confirm(self) -> None:
        if self.status != "PENDING":
            raise ReservationError("Only pending reservations can be confirmed.")
        if not self.service.available:
            raise ServiceUnavailableError("The service is currently unavailable.")
        self.status = "CONFIRMED"
        logger.info("Reservation confirmed: %s", self.identifier)

    def cancel(self) -> None:
        if self.status == "CANCELLED":
            raise ReservationError("Reservation was already cancelled.")
        self.status = "CANCELLED"
        logger.info("Reservation cancelled: %s", self.identifier)


class BookingSystem:
    """Business operations use lists; nothing is saved to a database."""

    def __init__(self) -> None:
        self.clients: list[Client] = []
        self.services: list[Service] = []
        self.reservations: list[Reservation] = []
        self.events: list[str] = []
        self._sequence = 1

    def record(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {message}")
        logger.info(message)

    def add_client(self, client_id: str, name: str, email: str) -> Client:
        client = Client(client_id, name, email)
        if any(c.identifier == client.identifier for c in self.clients):
            raise DuplicateClientError(f"Client ID {client_id} already exists.")
        self.clients.append(client)
        self.record(f"Client registered: {client.identifier} ({client.name})")
        return client

    def add_service(self, kind: str, code: str, name: str, rate: object) -> Service:
        classes = {"Meeting Room": RoomReservationService,
                   "Equipment Rental": EquipmentRentalService,
                   "Consulting": ConsultingService}
        if kind not in classes:
            raise ValidationError("Choose a supported service type.")
        if any(s.identifier == str(code).strip() for s in self.services):
            raise ValidationError(f"Service code {code} already exists.")
        service = classes[kind](code, name, rate)
        self.services.append(service)
        self.record(f"Service created: {service.identifier} ({service.kind})")
        return service

    def find_client(self, client_id: str) -> Client:
        for client in self.clients:
            if client.identifier == str(client_id).strip():
                return client
        raise ClientNotFoundError(f"Client {client_id} was not found.")

    def find_service(self, code: str) -> Service:
        for service in self.services:
            if service.identifier == str(code).strip() and service.available:
                return service
        raise ServiceUnavailableError(f"Service {code} is unavailable or missing.")

    def book(self, client_id: str, service_code: str, duration: object,
             tax_rate: object = 0, discount_rate: object = 0) -> Reservation:
        client = self.find_client(client_id)
        service = self.find_service(service_code)
        hours = positive_number(duration, "Duration")
        total = service.calculate_cost(hours, tax_rate, discount_rate)
        reservation = Reservation(f"RSV-{self._sequence:04d}", client, service,
                                  hours, total)
        self._sequence += 1
        self.reservations.append(reservation)
        self.record(f"Reservation created: {reservation.identifier} | "
                    f"{client.name} | {service.name} | ${total:,.2f}")
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation:
        for reservation in self.reservations:
            if reservation.identifier == reservation_id:
                return reservation
        raise ReservationError("Reservation ID was not found.")


def run_simulation() -> tuple[BookingSystem, list[tuple[str, bool, str]]]:
    """Run at least 10 valid and invalid operations without stopping on errors."""
    system = BookingSystem()
    outcomes: list[tuple[str, bool, str]] = []

    def attempt(label: str, action) -> None:
        # try/except/else/finally: validation failures never stop later steps.
        try:
            result = action()
        except BusinessError as exc:
            outcomes.append((label, False, str(exc)))
            logger.error("Rejected simulation step %s: %s", label, exc, exc_info=True)
        except Exception as exc:
            outcomes.append((label, False, f"Unexpected error: {exc}"))
            logger.exception("Unexpected simulation error in %s", label)
        else:
            detail = getattr(result, "identifier", "Completed")
            outcomes.append((label, True, detail))
        finally:
            logger.info("Simulation step completed: %s", label)

    attempt("01 Valid client", lambda: system.add_client("CL-001", "Laura Moreno", "laura@example.com"))
    attempt("02 Duplicate client", lambda: system.add_client("CL-001", "Another Name", "other@example.com"))
    attempt("03 Invalid email", lambda: system.add_client("CL-002", "Carlos Ruiz", "invalid-email"))
    attempt("04 Second valid client", lambda: system.add_client("CL-002", "Carlos Ruiz", "carlos@example.com"))
    attempt("05 Meeting room service", lambda: system.add_service("Meeting Room", "SV-101", "Conference Room A", 75000))
    attempt("06 Equipment rental service", lambda: system.add_service("Equipment Rental", "SV-102", "Camera Kit", 42000))
    attempt("07 Consulting service", lambda: system.add_service("Consulting", "SV-103", "Software Architecture", 95000))
    attempt("08 Invalid service rate", lambda: system.add_service("Consulting", "SV-104", "Broken Service", -500))
    attempt("09 Valid reservation", lambda: system.book("CL-001", "SV-101", 2))
    attempt("10 Missing client", lambda: system.book("CL-999", "SV-101", 2))
    attempt("11 Invalid duration", lambda: system.book("CL-002", "SV-102", 200))
    attempt("12 Valid discounted reservation", lambda: system.book("CL-002", "SV-103", 3, 0.19, 0.10))
    attempt("13 Confirm reservation", lambda: system.get_reservation("RSV-0001").confirm())
    attempt("14 Cancel reservation", lambda: system.get_reservation("RSV-0001").cancel())
    attempt("15 Repeat cancellation", lambda: system.get_reservation("RSV-0001").cancel())
    attempt("16 Missing service", lambda: system.book("CL-001", "SV-999", 2))
    return system, outcomes


# --- Desktop interface: simple operation tabs and visible activity log. ---
class SoftwareFJApp:
    BG = "#EEF5F3"
    DEEP = "#12594E"
    TEAL = "#138D78"
    INK = "#203E37"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Software FJ | Client & Reservation Manager")
        self.root.geometry("1120x780")
        self.root.minsize(950, 680)
        self.root.configure(bg=self.BG)
        self.system = BookingSystem()
        self._seed_data()
        self._styles()
        self._layout()
        self.refresh()

    def _seed_data(self) -> None:
        self.system.add_client("CL-001", "Laura Moreno", "laura@example.com")
        self.system.add_client("CL-002", "Carlos Ruiz", "carlos@example.com")
        self.system.add_service("Meeting Room", "SV-101", "Conference Room A", 75000)
        self.system.add_service("Equipment Rental", "SV-102", "Camera Kit", 42000)
        self.system.add_service("Consulting", "SV-103", "Software Architecture", 95000)

    def _styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"), padding=(20, 10))
        style.map("TNotebook.Tab", background=[("selected", "#D6EDE5")])
        style.configure("FJ.Treeview", rowheight=30, font=("Segoe UI", 10),
                        background="white", fieldbackground="white", foreground=self.INK)
        style.configure("FJ.Treeview.Heading", font=("Segoe UI", 10, "bold"),
                        background=self.DEEP, foreground="white")
        style.map("FJ.Treeview", background=[("selected", self.TEAL)],
                  foreground=[("selected", "white")])
        style.configure("FJ.TCombobox", font=("Segoe UI", 10))

    def _layout(self) -> None:
        tk.Label(self.root, text="SOFTWARE FJ", bg=self.DEEP, fg="white",
                 font=("Segoe UI", 26, "bold"), pady=14).pack(fill="x")
        tk.Label(self.root, text="CLIENTS  •  SERVICES  •  RESERVATIONS  •  ERROR HANDLING",
                 bg=self.BG, fg=self.DEEP, font=("Segoe UI", 11, "bold"),
                 pady=9).pack(fill="x")
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(3, 18))
        for label, builder in (("Clients", self._clients_tab),
                               ("Services", self._services_tab),
                               ("Reservations", self._reservations_tab),
                               ("Activity & Tests", self._activity_tab)):
            tab = tk.Frame(self.tabs, bg="white")
            self.tabs.add(tab, text=label)
            builder(tab)

    def _header(self, parent, text, subtitle):
        tk.Label(parent, text=text, bg="white", fg=self.DEEP,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=24, pady=(18, 2))
        tk.Label(parent, text=subtitle, bg="white", fg="#53665F",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(0, 13))

    def _form_row(self, frame, row, caption, default=""):
        tk.Label(frame, text=caption, bg="white", fg=self.INK,
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=6)
        entry = ttk.Entry(frame, width=29, font=("Segoe UI", 10))
        entry.grid(row=row, column=1, padx=(15, 0), pady=6)
        if default:
            entry.insert(0, default)
        return entry


    def _button(self, parent, text, callback):
        button = tk.Button(
            parent,
            text=text,
            command=callback,
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg=self.TEAL,
            activebackground=self.DEEP,
            activeforeground="white",
            relief="flat",
            padx=19,
            pady=9,
            cursor="hand2"
        )

        # Use the same geometry manager as existing widgets
        if parent.grid_slaves():
            button.grid(
                row=99,
                column=0,
                columnspan=2,
                sticky="w",
                pady=(12, 5)
            )
        else:
            button.pack(anchor="w", pady=(12, 5))

        return button


    def _tree(self, parent, columns, headings, widths):
        # Create a container for the data table
        frame = tk.Frame(parent, bg="white")
        frame.pack(fill="both", expand=True, padx=24, pady=(10, 20))

        # Create the table
        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            style="FJ.Treeview"
        )

        # Configure table headings and column widths
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=80)

        tree.pack(side="left", fill="both", expand=True)

        # Add a vertical scrollbar
        scroll = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=tree.yview
        )
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)

        return tree


    def _clients_tab(self, tab):
        self._header(tab, "Client registration", "Validated fields and protected client details")
        form = tk.Frame(tab, bg="white")
        form.pack(anchor="w", padx=24)
        self.client_id_entry = self._form_row(form, 0, "Client ID")
        self.client_name_entry = self._form_row(form, 1, "Full name")
        self.client_email_entry = self._form_row(form, 2, "Email")
        self._button(form, "REGISTER CLIENT", self.add_client)
        self.clients_tree = self._tree(tab, ("id", "name", "email"),
                                       ("Client ID", "Full name", "Email"), (150, 270, 340))

    def _services_tab(self, tab):
        self._header(tab, "Service catalog", "Create specialized services with validated pricing")
        form = tk.Frame(tab, bg="white")
        form.pack(anchor="w", padx=24)
        tk.Label(form, text="Service type", bg="white", fg=self.INK,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.service_kind = ttk.Combobox(form, values=["Meeting Room", "Equipment Rental", "Consulting"],
                                         state="readonly", width=26)
        self.service_kind.current(0)
        self.service_kind.grid(row=0, column=1, padx=(15, 0), pady=6)
        self.service_code_entry = self._form_row(form, 1, "Service code")
        self.service_name_entry = self._form_row(form, 2, "Service name")
        self.service_rate_entry = self._form_row(form, 3, "Hourly rate (COP)")
        self._button(form, "ADD SERVICE", self.add_service)
        self.services_tree = self._tree(tab, ("code", "kind", "name", "rate", "status"),
                                        ("Code", "Type", "Name", "Rate (COP)", "Status"),
                                        (105, 155, 235, 140, 100))

    def _reservations_tab(self, tab):
        self._header(tab, "Reservation manager", "Book, confirm, cancel, calculate tax and discounts")
        form = tk.Frame(tab, bg="white")
        form.pack(anchor="w", padx=24)
        self.booking_client_entry = self._form_row(form, 0, "Client ID", "CL-001")
        self.booking_service_entry = self._form_row(form, 1, "Service code", "SV-101")
        self.booking_duration_entry = self._form_row(form, 2, "Duration (hours)", "2")
        self.booking_tax_entry = self._form_row(form, 3, "Tax rate (0–1)", "0")
        self.booking_discount_entry = self._form_row(form, 4, "Discount rate (0–1)", "0")
        buttons = tk.Frame(tab, bg="white")
        buttons.pack(anchor="w", padx=24)
        for text, callback in (("CREATE RESERVATION", self.create_reservation),
                               ("CONFIRM SELECTED", self.confirm_selected),
                               ("CANCEL SELECTED", self.cancel_selected)):
            button = tk.Button(buttons, text=text, command=callback, bg=self.TEAL,
                               fg="white", activebackground=self.DEEP, activeforeground="white",
                               font=("Segoe UI", 9, "bold"), relief="flat", padx=13, pady=8)
            button.pack(side="left", padx=(0, 10), pady=(6, 3))
        self.reservations_tree = self._tree(tab,
            ("id", "client", "service", "duration", "total", "status"),
            ("Reservation", "Client", "Service", "Hours", "Total (COP)", "Status"),
            (120, 160, 190, 75, 155, 120))

    def _activity_tab(self, tab):
        self._header(tab, "Activity & validation", "Automatic 16-step exception-handling demonstration")
        toolbar = tk.Frame(tab, bg="white")
        toolbar.pack(fill="x", padx=24)
        self._button(toolbar, "RUN 16 SIMULATED OPERATIONS", self.run_demo)
        self.activity_text = tk.Text(tab, font=("Consolas", 10), bg="#F7FBF9",
                                     fg=self.INK, relief="flat", padx=16, pady=14,
                                     height=18, wrap="word")
        self.activity_text.pack(fill="both", expand=True, padx=24, pady=(10, 18))

    def _handle(self, label, action) -> None:
        try:
            result = action()
        except BusinessError as exc:
            logger.error("%s rejected: %s", label, exc, exc_info=True)
            messagebox.showerror("Validation error", str(exc), parent=self.root)
        except Exception as exc:
            logger.exception("Unexpected error during %s", label)
            messagebox.showerror("Unexpected error", "Operation failed. See the event log.",
                                 parent=self.root)
        else:
            identifier = getattr(result, "identifier", "")
            messagebox.showinfo("Success", f"{label} completed. {identifier}", parent=self.root)
            self.refresh()
        finally:
            logger.info("GUI operation finished: %s", label)

    def add_client(self):
        self._handle("Client registration", lambda: self.system.add_client(
            self.client_id_entry.get(), self.client_name_entry.get(), self.client_email_entry.get()))

    def add_service(self):
        self._handle("Service creation", lambda: self.system.add_service(
            self.service_kind.get(), self.service_code_entry.get(),
            self.service_name_entry.get(), self.service_rate_entry.get()))

    def create_reservation(self):
        self._handle("Reservation creation", lambda: self.system.book(
            self.booking_client_entry.get(), self.booking_service_entry.get(),
            self.booking_duration_entry.get(), self.booking_tax_entry.get(),
            self.booking_discount_entry.get()))

    def _selected_reservation(self) -> Reservation:
        selected = self.reservations_tree.selection()
        if not selected:
            raise ReservationError("Select a reservation in the table first.")
        reservation_id = self.reservations_tree.item(selected[0], "values")[0]
        return self.system.get_reservation(reservation_id)

    def confirm_selected(self):
        self._handle("Reservation confirmation", lambda: self._selected_reservation().confirm())

    def cancel_selected(self):
        self._handle("Reservation cancellation", lambda: self._selected_reservation().cancel())

    def run_demo(self):
        system, outcomes = run_simulation()
        self.activity_text.delete("1.0", tk.END)
        for label, success, description in outcomes:
            icon = "PASS" if success else "HANDLED ERROR"
            self.activity_text.insert(tk.END, f"{label:<35} [{icon}] {description}\n\n")
        good = sum(1 for _, success, _ in outcomes if success)
        self.activity_text.insert(tk.END, f"COMPLETE: {len(outcomes)} operations | "
                                               f"{good} successful | {len(outcomes)-good} "
                                               "errors handled | app remains active\n")
        self.activity_text.insert(tk.END, f"\nEvents written to: {LOG_FILE.name}\n")
        self.system.record(f"Demonstration completed: {len(outcomes)} simulated operations")

    def refresh(self):
        for tree in (self.clients_tree, self.services_tree, self.reservations_tree):
            tree.delete(*tree.get_children())
        for c in self.system.clients:
            self.clients_tree.insert("", "end", values=(c.identifier, c.name, c.email))
        for s in self.system.services:
            self.services_tree.insert("", "end", values=(s.identifier, s.kind, s.name,
                                                        f"${s.hourly_rate:,.2f}",
                                                        "Available" if s.available else "Unavailable"))
        for r in self.system.reservations:
            self.reservations_tree.insert("", "end", values=(r.identifier, r.client.name,
                                                             r.service.name, r.duration,
                                                             f"${r.total:,.2f}", r.status))


def main() -> None:
    parser = argparse.ArgumentParser(description="Software FJ reservation management")
    parser.add_argument("--demo", action="store_true", help="Run 16 simulation steps without GUI")
    args = parser.parse_args()
    if args.demo:
        _, outcomes = run_simulation()
        for label, success, detail in outcomes:
            print(f"{'PASS' if success else 'HANDLED ERROR':13} | {label} | {detail}")
        print(f"\n{len(outcomes)} operations completed. Log: {LOG_FILE}")
    else:
        root = tk.Tk()
        SoftwareFJApp(root)
        root.mainloop()


if __name__ == "__main__":
    main()
