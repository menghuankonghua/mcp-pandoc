import pypandoc
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
# from pydantic import AnyUrl # Not strictly used, can be removed if not needed elsewhere
import mcp.server.stdio
import os
import asyncio
from aiohttp import web
import logging
from urllib.parse import urlparse

# --- Configuration ---
# These should ideally be set via environment variables for flexibility

# CRITICAL: Print environment variables as Python sees them, very early.
print(f"PYTHON SCRIPT STARTING: Attempting to read environment variables.")
print(f"PYTHON SCRIPT: Raw MCP_PANDOC_SHARED_DIR: {os.environ.get('MCP_PANDOC_SHARED_DIR')}")
print(f"PYTHON SCRIPT: Raw MCP_PANDOC_DOWNLOAD_BASE_URL: {os.environ.get('MCP_PANDOC_DOWNLOAD_BASE_URL')}")
print(f"PYTHON SCRIPT: Raw MCP_PANDOC_HTTP_PORT: {os.environ.get('MCP_PANDOC_HTTP_PORT')}")

# Default internal path inside the container where files will be stored for download
SHARED_DOWNLOAD_INTERNAL_PATH = os.environ.get("MCP_PANDOC_SHARED_DIR", "/app/shared_downloads")
# Base URL for constructing download links (e.g., http://localhost:8081/downloads or https://your-domain.com/downloads)
# This needs to be the URL through which the client can reach the HTTP server
DOWNLOAD_BASE_URL = os.environ.get("MCP_PANDOC_DOWNLOAD_BASE_URL", "http://localhost:8081/downloads")
# Port for the internal HTTP server
HTTP_SERVER_PORT = int(os.environ.get("MCP_PANDOC_HTTP_PORT", 8081))

print(f"PYTHON SCRIPT: Effective SHARED_DOWNLOAD_INTERNAL_PATH: {SHARED_DOWNLOAD_INTERNAL_PATH}")
print(f"PYTHON SCRIPT: Effective DOWNLOAD_BASE_URL: {DOWNLOAD_BASE_URL}")
print(f"PYTHON SCRIPT: Effective HTTP_SERVER_PORT: {HTTP_SERVER_PORT}")
# --- End Configuration ---

# Ensure the shared download directory exists
os.makedirs(SHARED_DOWNLOAD_INTERNAL_PATH, exist_ok=True)

server = Server("mcp-pandoc")
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp-pandoc-server")


async def start_http_server(app_runner):
    """Starts the aiohttp server."""
    await app_runner.setup()
    site = web.TCPSite(app_runner, '0.0.0.0', HTTP_SERVER_PORT)  # Listen on all interfaces inside container
    await site.start()
    logger.info(f"HTTP server started on 0.0.0.0:{HTTP_SERVER_PORT}, serving static files.")
    # This log message is crucial for debugging the download link construction
    logger.info(f"Download links will be based on (DOWNLOAD_BASE_URL): {DOWNLOAD_BASE_URL}")
    logger.info(f"Files are served from internal path: {SHARED_DOWNLOAD_INTERNAL_PATH}")


async def cleanup_http_server(app_runner):
    """Cleans up the aiohttp server."""
    await app_runner.cleanup()
    logger.info("HTTP server stopped.")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="convert-contents",
            description=(
                "Converts content between different formats. Transforms input content from any supported format "
                "into the specified output format.\n\n"
                "🚨 CRITICAL REQUIREMENTS - PLEASE READ:\n"
                "1. PDF Conversion:\n"
                "   * You MUST install TeX Live BEFORE attempting PDF conversion:\n"
                "   * Ubuntu/Debian: `sudo apt-get install texlive-xetex texlive-fonts-recommended texlive-lang-chinese` (added Chinese support for TeX)\n"
                "   * macOS: `brew install texlive`\n"
                "   * Windows: Install MiKTeX or TeX Live from https://miktex.org/ or https://tug.org/texlive/\n"
                "   * PDF conversion will FAIL without this installation\n\n"
                "2. File Paths - EXPLICIT REQUIREMENTS:\n"
                "   * When asked to save or convert to a file, you MUST provide:\n"
                "     - Complete directory path (this will be used for the filename if unique names are desired)\n"
                "     - Filename\n"
                "     - File extension\n"
                "   * Example request: 'Write a story and save as PDF as /output/story.pdf'\n"
                "   * You MUST specify: '/path/to/story.pdf' or 'C:\\Documents\\story.pdf'. The filename part (e.g., 'story.pdf') will be used.\n"
                "   * The tool will NOT automatically generate filenames or extensions\n\n"
                "3. File Location After Conversion:\n"
                "   * After successful conversion to a file, the tool will display the exact path where the file is saved INTERNALLY "
                "     and provide a DOWNLOAD LINK.\n"
                "   * Look for message: 'Content successfully converted. Download from: [download_link]'\n"
                "   * You can use the provided link to download your converted file.\n"
                "   * If no output path is specified (for basic formats), files are NOT saved and content is returned directly.\n"
                "   * For better control and to get a download link, always provide explicit output file paths for advanced formats.\n\n"
                "Supported formats:\n"
                "- Basic formats (content returned directly if no output_file): txt, html, markdown\n"
                "- Advanced formats (REQUIRE complete file paths, download link provided): pdf, docx, rst, latex, epub\n\n"
                "✅ CORRECT Usage Examples:\n"
                "1. 'Convert this text to HTML' (basic conversion)\n"
                "   - Tool will show converted content\n\n"
                "2. 'Save this text as PDF at /documents/story.pdf'\n"
                "   - Correct: specifies path + filename + extension\n"
                "   - Tool will show: 'Content successfully converted. Download from: [link_to_story.pdf]'\n\n"
                "❌ INCORRECT Usage Examples:\n"
                "1. 'Save this as PDF in /documents/' (for advanced formats)\n"
                "   - Missing filename and extension\n"
                "2. 'Convert to PDF' (for advanced formats)\n"
                "   - Missing complete file path\n\n"
                "When requesting conversion, ALWAYS specify:\n"
                "1. The content or input file\n"
                "2. The desired output format\n"
                "3. For advanced formats (to get a download link): complete output path + filename + extension\n"
                "Example: 'Convert this markdown to PDF and save as /path/to/output.pdf'\n\n"
                "Note: After conversion, always check the success message for the download link or converted content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "contents": {
                        "type": "string",
                        "description": "The content to be converted (required if input_file not provided)"
                    },
                    "input_file": {
                        "type": "string",
                        "description": "Complete path to input file including filename and extension (e.g., '/path/to/input.md')"
                    },
                    "input_format": {
                        "type": "string",
                        "description": "Source format of the content (defaults to markdown)",
                        "default": "markdown",
                        "enum": ["markdown", "html", "pdf", "docx", "rst", "latex", "epub", "txt"]
                    },
                    "output_format": {
                        "type": "string",
                        "description": "Desired output format (defaults to markdown)",
                        "default": "markdown",
                        "enum": ["markdown", "html", "pdf", "docx", "rst", "latex", "epub", "txt"]
                    },
                    "output_file": {
                        "type": "string",
                        "description": (
                            "Complete path where to save the output including filename and extension "
                            "(e.g., '/desired/path/output.pdf'). The filename part (e.g. 'output.pdf') "
                            "will be used for the downloadable file. Required for pdf, docx, rst, latex, epub formats."
                        )
                    }
                },
                "oneOf": [
                    {"required": ["contents"]},
                    {"required": ["input_file"]}
                ],
                "allOf": [
                    {
                        "if": {
                            "properties": {
                                "output_format": {
                                    "enum": ["pdf", "docx", "rst", "latex", "epub"]
                                }
                            }
                        },
                        "then": {
                            "required": ["output_file"]
                        }
                    }
                ]
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(
        name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name not in ["convert-contents"]:
        raise ValueError(f"Unknown tool: {name}")

    logger.info(f"Received arguments for tool '{name}': {arguments}")

    if not arguments:
        raise ValueError("Missing arguments")

    contents = arguments.get("contents")
    input_file_path = arguments.get("input_file")
    user_specified_output_file = arguments.get("output_file")
    output_format = arguments.get("output_format", "markdown").lower()
    input_format = arguments.get("input_format", "markdown").lower()

    if not contents and not input_file_path:
        raise ValueError("Either 'contents' or 'input_file' must be provided")

    SUPPORTED_FORMATS = {'html', 'markdown', 'pdf', 'docx', 'rst', 'latex', 'epub', 'txt'}
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported output format: '{output_format}'. Supported formats are: {', '.join(SUPPORTED_FORMATS)}")

    ADVANCED_FORMATS = {'pdf', 'docx', 'rst', 'latex', 'epub'}
    if output_format in ADVANCED_FORMATS and not user_specified_output_file:
        raise ValueError(f"output_file path is required for {output_format} format to enable download.")

    actual_output_path_in_container = None
    download_url = None
    output_filename_for_url = None  # Store sanitized filename for URL

    if user_specified_output_file:
        # Use only the filename part from the user's specified path.
        # This filename is used for storage in SHARED_DOWNLOAD_INTERNAL_PATH and for the download link.
        output_filename_for_url = os.path.basename(user_specified_output_file)
        if not output_filename_for_url:
            raise ValueError("output_file must include a filename and extension.")

        # Ensure filename is safe for URL and filesystem (basic sanitation)
        # For more robust sanitation, consider a library or more rules.
        # This example primarily handles spaces by URL encoding later.
        actual_output_path_in_container = os.path.join(SHARED_DOWNLOAD_INTERNAL_PATH, output_filename_for_url)

        # Construct download URL. The filename part will be URL-encoded by the browser/client if it contains spaces or special chars.
        # The DOWNLOAD_BASE_URL should already contain the necessary prefix like /downloads
        download_url = f"{DOWNLOAD_BASE_URL.rstrip('/')}/{output_filename_for_url}"
        logger.info(f"User specified output file: {user_specified_output_file}")
        logger.info(f"Derived output filename for URL/storage: {output_filename_for_url}")
        logger.info(f"Internal save path: {actual_output_path_in_container}")
        logger.info(f"Constructed download URL: {download_url}")

    try:
        extra_args = []
        # For PDF conversion, especially with CJK characters, xelatex is better.
        # Ensure fonts are installed in the Docker image (e.g., Noto Sans CJK or other Chinese fonts)
        if output_format == "pdf":
            extra_args.extend([
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=1in",
                # Example: If you have a main CJK font installed and know its name
                # "-V", "mainfont=Noto Sans CJK SC" # Or your specific font
                # "-V", "monofont=Noto Sans Mono CJK SC"
                # "-V", "sansfont=Noto Sans CJK SC"
            ])
            # If input is markdown, add CJK support for pandoc's markdown parser
            if input_format == "markdown":
                extra_args.append("--from=markdown+east_asian_line_breaks")

        converted_output_string = None

        if input_file_path:
            if not os.path.exists(input_file_path):
                raise ValueError(f"Input file not found: {input_file_path}")
            logger.info(f"Converting from input file: {input_file_path}")
            if actual_output_path_in_container:
                pypandoc.convert_file(
                    input_file_path,
                    output_format,
                    outputfile=actual_output_path_in_container,
                    extra_args=extra_args
                )
                logger.info(
                    f"File successfully converted from '{input_file_path}' and saved to: {actual_output_path_in_container}")
            else:
                converted_output_string = pypandoc.convert_file(
                    input_file_path,
                    output_format,
                    extra_args=extra_args
                )
        else:  # contents must be provided
            logger.info(f"Converting from direct content string (input format: {input_format})")
            if actual_output_path_in_container:
                pypandoc.convert_text(
                    contents,
                    output_format,
                    format=input_format,
                    outputfile=actual_output_path_in_container,
                    extra_args=extra_args
                )
                logger.info(f"Content successfully converted and saved to: {actual_output_path_in_container}")
            else:
                converted_output_string = pypandoc.convert_text(
                    contents,
                    output_format,
                    format=input_format,
                    extra_args=extra_args
                )

        if actual_output_path_in_container and download_url:
            notify_with_result = (
                f"Content successfully converted. "
                f"Download from: {download_url}\n"
                f"(Internally saved at: {actual_output_path_in_container})"
            )
        elif converted_output_string is not None:
            if not converted_output_string.strip():
                logger.warning(f"Conversion resulted in empty output for format {output_format}")
                notify_with_result = (
                    f"Conversion to {output_format} resulted in empty content. "
                    "This might be expected or indicate an issue (e.g., missing fonts for PDF with CJK)."
                )
            else:
                notify_with_result = (
                    f'Following are the converted contents in {output_format} format.\n'
                    f'If you want to save this as a file and get a download link, '
                    f'please provide the `output_file` parameter with a complete path (e.g., "/path/to/my_document.{output_format}").\n\n'
                    f'Converted Contents:\n\n{converted_output_string}'
                )
        else:
            raise ValueError("Conversion process completed but no output (file or string) was generated.")

        return [types.TextContent(type="text", text=notify_with_result)]

    except Exception as e:
        error_msg = f"Error converting {'file ' + input_file_path if input_file_path else 'contents'} from {input_format} to {output_format}: {str(e)}"
        logger.error(error_msg, exc_info=True)  # Log full traceback
        raise ValueError(error_msg)


async def main():
    logger.info(f"MCP Pandoc Server starting up...")
    logger.info(f"Using DOWNLOAD_BASE_URL: {DOWNLOAD_BASE_URL}")
    logger.info(f"Serving files from internal path: {SHARED_DOWNLOAD_INTERNAL_PATH} on port {HTTP_SERVER_PORT}")

    http_app = web.Application()

    # Determine the route prefix for serving static files from DOWNLOAD_BASE_URL
    # Example: DOWNLOAD_BASE_URL = "http://172.191.18.52:8087/downloads"
    # parsed_base_url.path will be "/downloads"
    # This path is what aiohttp will use as its route prefix.
    parsed_base_url = urlparse(DOWNLOAD_BASE_URL)
    http_server_route_prefix = parsed_base_url.path.rstrip('/')
    if not http_server_route_prefix:  # If DOWNLOAD_BASE_URL is like http://host:port (no path)
        # This case means files are served at the root of the HTTP server.
        # The download link would be http://host:port/filename.pdf
        # And aiohttp serves SHARED_DOWNLOAD_INTERNAL_PATH at '/'
        http_server_route_prefix = '/'
        logger.warning(
            "DOWNLOAD_BASE_URL does not specify a path prefix (e.g., /downloads). "
            "Files will be served from HTTP server root. "
            f"Ensure '{DOWNLOAD_BASE_URL}' is accessible and correctly points to where files will be."
        )
    else:
        logger.info(f"HTTP server will serve files under the route prefix: '{http_server_route_prefix}'")

    # Setup static file serving
    # Files in SHARED_DOWNLOAD_INTERNAL_PATH will be accessible via:
    # <protocol>://<host>:<port><http_server_route_prefix>/<filename>
    # This must match the structure of DOWNLOAD_BASE_URL
    http_app.router.add_static(
        prefix=http_server_route_prefix,
        path=SHARED_DOWNLOAD_INTERNAL_PATH,
        show_index=True,  # Helpful for debugging, list files if index.html not found
        follow_symlinks=True  # Be cautious with symlinks if any are used
    )
    logger.info(
        f"aiohttp static route configured: prefix='{http_server_route_prefix}', path='{SHARED_DOWNLOAD_INTERNAL_PATH}'")

    app_runner = web.AppRunner(http_app)
    http_server_task = asyncio.create_task(start_http_server(app_runner))

    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-pandoc",
                    server_version="0.2.1",  # Version bump
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        logger.critical(f"MCP server run failed: {e}", exc_info=True)
    finally:
        logger.info("MCP Pandoc Server shutting down...")
        await cleanup_http_server(app_runner)
        if http_server_task and not http_server_task.done():
            http_server_task.cancel()
            try:
                await http_server_task
            except asyncio.CancelledError:
                logger.info("HTTP server task successfully cancelled.")
            except Exception as e_cancel:
                logger.error(f"Error during HTTP server task cancellation: {e_cancel}", exc_info=True)
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user (KeyboardInterrupt).")
    except Exception as e_global:
        logger.critical(f"Unhandled exception in __main__: {e_global}", exc_info=True)
