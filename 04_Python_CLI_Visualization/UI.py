import time

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
except ImportError:
    RICH_AVAILABLE = False
else:
    RICH_AVAILABLE = True

import main_cli as audio


console = Console() if RICH_AVAILABLE else None


def header():
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white", no_wrap=True)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(style="white", no_wrap=True)
    table.add_row("Port", audio.PORT, "Baud", f"{audio.BAUD:,} bps")
    table.add_row("Sample Rate", f"{audio.OUTPUT_FS} Hz", "Bit Depth", f"{audio.BIT_DEPTH}-bit")
    table.add_row("Team ID", audio.TEAM_ID, "Converter", audio.CONVERTER_SOURCE)
    return Panel(
        table,
        title="[bold cyan]Dual-STM Audio System[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
    )


def get_output_preferences():
    console.print("\n[bold]Select output formats[/bold]")
    options = []
    if console.input("Generate WAV? [bold cyan](y/n)[/bold cyan]: ").strip().lower() == "y":
        options.append("WAV")
    if console.input("Generate PNG waveform? [bold cyan](y/n)[/bold cyan]: ").strip().lower() == "y":
        options.append("PNG")
    if console.input("Generate CSV? [bold cyan](y/n)[/bold cyan]: ").strip().lower() == "y":
        options.append("CSV")
    return options


def capture_for_duration(ser, duration):
    chunks = []
    ser.reset_input_buffer()
    time.sleep(0.05)

    got_ack, seen = audio.send_command_and_wait_for_ack(ser, b"M")
    if got_ack:
        console.print("[green]Processing STM acknowledged manual start.[/green]")
    else:
        console.print("[yellow]Warning: no ACK:M from Processing STM. Continuing capture anyway.[/yellow]")
        if seen:
            console.print(f"[dim]Received before audio capture: {seen!r}[/dim]")
    ser.reset_input_buffer()

    start_time = time.monotonic()
    deadline = start_time + duration
    byte_goal = int(audio.OUTPUT_FS * audio.SAMPLE_WIDTH_BYTES * duration)

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task("Recording", total=max(duration, 0.001))
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            target_bytes = int(audio.NOMINAL_FS * audio.SAMPLE_WIDTH_BYTES * min(0.05, max(0.001, remaining)))
            chunk = ser.read(max(audio.SAMPLE_WIDTH_BYTES, min(8192, target_bytes)))
            if chunk:
                chunks.append(chunk)
            elapsed_now = min(duration, time.monotonic() - start_time)
            captured = sum(len(chunk) for chunk in chunks)
            progress.update(task, completed=elapsed_now, description=f"Recording {captured:,}/{byte_goal:,} bytes")

    elapsed = time.monotonic() - start_time
    ser.write(b"S")
    ser.flush()

    raw_data = b"".join(chunks)
    sample_count = len(raw_data) // audio.SAMPLE_WIDTH_BYTES
    return raw_data, audio.measured_sample_rate(sample_count, elapsed), elapsed


def manual_recording_mode():
    console.rule("[bold cyan]Manual Recording Mode[/bold cyan]")
    try:
        duration = float(console.input("Enter recording duration in seconds: ").strip())
    except ValueError:
        console.print("[red]Invalid duration.[/red]")
        return

    options = get_output_preferences()
    try:
        with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=0.02) as ser:
            console.input("\nPress Enter to START recording...")
            raw_data, measured_rate, elapsed = capture_for_duration(ser, duration)
            console.print(f"[green]Recording complete.[/green] Captured {len(raw_data):,} bytes in {elapsed:.2f}s.")

        audio.process_outputs(raw_data, options, "Manual Mode", measured_rate)
    except Exception as exc:
        console.print(f"[red]Serial/processing error:[/red] {exc}")


def distance_trigger_mode():
    console.rule("[bold cyan]Distance Trigger Mode[/bold cyan]")
    options = get_output_preferences()
    console.print("\nRecording starts while the ultrasonic sensor is within 10 cm.")
    console.print("Press Ctrl+C to exit distance mode.\n")

    try:
        with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=0.05) as ser:
            ser.reset_input_buffer()
            got_ack, seen = audio.send_command_and_wait_for_ack(ser, b"D")
            if got_ack:
                console.print("[green]Processing STM acknowledged distance mode.[/green]")
            else:
                console.print("[yellow]Warning: no ACK:D from Processing STM.[/yellow]")
                if seen:
                    console.print(f"[dim]Received before distance capture: {seen!r}[/dim]")

            trigger_num = 0
            while True:
                with console.status("[cyan]Waiting for proximity trigger...[/cyan]"):
                    first = b""
                    while len(first) < audio.SAMPLE_WIDTH_BYTES:
                        first = ser.read(audio.SAMPLE_WIDTH_BYTES)

                trigger_num += 1
                console.print(f"\n[bold green]Trigger #{trigger_num} detected. Recording started...[/bold green]")
                chunks = [first]
                recording_start = time.monotonic()
                last_data_time = recording_start

                with console.status("[green]Recording until object leaves threshold...[/green]"):
                    while True:
                        chunk = ser.read(8192)
                        if chunk:
                            chunks.append(chunk)
                            last_data_time = time.monotonic()
                        else:
                            break

                raw_data = b"".join(chunks)
                elapsed = max(0.001, last_data_time - recording_start)
                measured_rate = audio.measured_sample_rate(len(raw_data) // audio.SAMPLE_WIDTH_BYTES, elapsed)
                console.print(f"[green]Object left. Recording stopped.[/green] Captured {len(raw_data):,} bytes.")
                audio.process_outputs(raw_data, options, f"Distance Trigger {trigger_num}", measured_rate)

    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting Distance Trigger Mode.[/yellow]")
        try:
            with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=1) as ser:
                ser.write(b"S")
        except Exception:
            pass
    except Exception as exc:
        console.print(f"[red]Serial/processing error:[/red] {exc}")


def main():
    if not RICH_AVAILABLE:
        print("Rich is not installed. Falling back to the standard CLI.")
        print("Install the enhanced UI with: pip install rich")
        audio.main()
        return

    console.clear()
    console.print(header())

    while True:
        menu = Table(title="Main Menu", box=box.SIMPLE, show_header=False)
        menu.add_column("Key", style="bold cyan", width=4)
        menu.add_column("Action")
        menu.add_row("1", "Manual Recording Mode")
        menu.add_row("2", "Distance Trigger Mode")
        menu.add_row("q", "Quit Program")
        console.print(menu)

        choice = console.input("Please enter your choice: ").strip().lower()
        if choice == "1":
            manual_recording_mode()
        elif choice == "2":
            distance_trigger_mode()
        elif choice == "q":
            try:
                with audio.serial.Serial(audio.PORT, audio.BAUD, timeout=1) as ser:
                    ser.write(b"S")
            except Exception:
                pass
            console.print("[green]Exiting program. Goodbye![/green]")
            break
        else:
            console.print("[red]Invalid input, please try again.[/red]")


if __name__ == "__main__":
    main()
