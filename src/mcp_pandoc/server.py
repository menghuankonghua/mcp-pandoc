import pypandoc
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import os
import asyncio
from aiohttp import web
import logging  # For better logging

# --- Configuration ---
# These should ideally be set via environment variables for flexibility
# Default internal path inside the container where files will be stored for download
# SHARED_DOWNLOAD_INTERNAL_PATH = os.environ.get("MCP_PANDOC_SHARED_DIR", "/app/shared_downloads")
SHARED_DOWNLOAD_INTERNAL_PATH = os.environ.get("MCP_PANDOC_SHARED_DIR", "/home/jasonzhou/shared_downloads")
# Base URL for constructing download links (e.g., http://localhost:8081/downloads or https://your-domain.com/downloads)
# This needs to be the URL through which the client can reach the HTTP server
DOWNLOAD_BASE_URL = os.environ.get("MCP_PANDOC_DOWNLOAD_BASE_URL", "http://localhost:8081/downloads")
# Port for the internal HTTP server
HTTP_SERVER_PORT = int(os.environ.get("MCP_PANDOC_HTTP_PORT", 8081))
# --- End Configuration ---

# Ensure the shared download directory exists
os.makedirs(SHARED_DOWNLOAD_INTERNAL_PATH, exist_ok=True)

server = Server("mcp-pandoc")
logger = logging.getLogger("mcp-pandoc-server")
logging.basicConfig(level=logging.INFO)


async def start_http_server(app_runner):
    """Starts the aiohttp server."""
    await app_runner.setup()
    site = web.TCPSite(app_runner, '0.0.0.0', HTTP_SERVER_PORT)
    await site.start()
    logger.info(f"HTTP server started on port {HTTP_SERVER_PORT}, serving from {SHARED_DOWNLOAD_INTERNAL_PATH}")
    logger.info(f"Download links will be based on: {DOWNLOAD_BASE_URL}")


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
                "   * Ubuntu/Debian: `sudo apt-get install texlive-xetex`\n"
                "   * macOS: `brew install texlive`\n"
                "   * Windows: Install MiKTeX or TeX Live from https://miktex.org/ or https://tug.org/texlive/\n"
                "   * PDF conversion will FAIL without this installation\n\n"
                "2. File Paths - EXPLICIT REQUIREMENTS:\n"
                "   * When asked to save or convert to a file, you MUST provide:\n"
                "     - Complete directory path (this will be used for the filename)\n"
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

    logger.info(f"Received arguments: {arguments}")

    if not arguments:
        raise ValueError("Missing arguments")

    contents = arguments.get("contents")
    input_file_path = arguments.get("input_file")  # Path from user for input
    user_specified_output_file = arguments.get("output_file")  # Path from user for output
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

    # This will be the actual path inside the container where the file is saved
    actual_output_path_in_container = None
    download_url = None

    if user_specified_output_file:
        # Use only the filename part from the user's specified path for storage and link
        output_filename = os.path.basename(user_specified_output_file)
        if not output_filename:  # Handle cases like "output_file": "/some/path/"
            raise ValueError("output_file must include a filename and extension.")
        actual_output_path_in_container = os.path.join(SHARED_DOWNLOAD_INTERNAL_PATH, output_filename)
        download_url = f"{DOWNLOAD_BASE_URL.rstrip('/')}/{output_filename}"

    try:
        extra_args = []
        if output_format == "pdf":
            extra_args.extend([
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=1in"
            ])

        converted_output_string = None  # To store string output if not saving to file

        if input_file_path:
            if not os.path.exists(input_file_path):
                raise ValueError(f"Input file not found: {input_file_path}")

            if actual_output_path_in_container:
                # Convert file to file (saved in shared download dir)
                pypandoc.convert_file(
                    input_file_path,
                    output_format,
                    outputfile=actual_output_path_in_container,
                    extra_args=extra_args
                )
                logger.info(
                    f"File successfully converted from {input_file_path} and saved to: {actual_output_path_in_container}")
            else:
                # Convert file to string
                converted_output_string = pypandoc.convert_file(
                    input_file_path,
                    output_format,
                    extra_args=extra_args
                )
        else:  # contents must be provided
            if actual_output_path_in_container:
                # Convert content to file (saved in shared download dir)
                pypandoc.convert_text(
                    contents,
                    output_format,
                    format=input_format,
                    outputfile=actual_output_path_in_container,
                    extra_args=extra_args
                )
                logger.info(f"Content successfully converted and saved to: {actual_output_path_in_container}")
            else:
                # Convert content to string
                converted_output_string = pypandoc.convert_text(
                    contents,
                    output_format,
                    format=input_format,
                    extra_args=extra_args
                )

        # Determine response
        if actual_output_path_in_container and download_url:
            notify_with_result = (
                f"Content successfully converted. "
                f"Download from: {download_url}\n"
                f"(Internally saved at: {actual_output_path_in_container})"
            )
        elif converted_output_string is not None:
            if not converted_output_string.strip():  # Check if output is empty or just whitespace
                logger.warning(f"Conversion resulted in empty output for format {output_format}")
                notify_with_result = (
                    f"Conversion to {output_format} resulted in empty content. "
                    "This might be expected for some format combinations or indicate an issue."
                )
            else:
                notify_with_result = (
                    f'Following are the converted contents in {output_format} format.\n'
                    f'If you want to save this as a file and get a download link, '
                    f'please provide the `output_file` parameter with a complete path (e.g., "/path/to/my_document.{output_format}").\n\n'
                    f'Converted Contents:\n\n{converted_output_string}'
                )
        else:
            # This case should ideally not be reached if logic is correct
            raise ValueError("Conversion process completed but no output (file or string) was generated.")

        return [
            types.TextContent(
                type="text",
                text=notify_with_result
            )
        ]

    except Exception as e:
        error_msg = f"Error converting {'file ' + input_file_path if input_file_path else 'contents'} from {input_format} to {output_format}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg)


async def main():
    # Setup aiohttp app for serving files
    http_app = web.Application()
    # Serve files from the SHARED_DOWNLOAD_INTERNAL_PATH under the '/downloads' route prefix,
    # but the DOWNLOAD_BASE_URL already includes '/downloads', so we serve from root of shared path
    # The URL structure will be DOWNLOAD_BASE_URL/<filename>
    # For aiohttp's add_static, the first argument is the URL prefix,
    # the second is the directory path.
    # If DOWNLOAD_BASE_URL is http://host:port/myfiles, and files are filename.pdf,
    # then add_static('/myfiles', SHARED_DOWNLOAD_INTERNAL_PATH)
    # Our DOWNLOAD_BASE_URL includes the prefix, so client constructs URL like DOWNLOAD_BASE_URL/filename.ext
    # The http server here serves from SHARED_DOWNLOAD_INTERNAL_PATH at its root.
    # The client will construct the full URL like DOWNLOAD_BASE_URL/filename.pdf
    # The important part is that whatever comes after DOWNLOAD_BASE_URL in the link
    # must match the file structure within SHARED_DOWNLOAD_INTERNAL_PATH.
    # Given DOWNLOAD_BASE_URL = "http://localhost:8081/downloads"
    # And file is "report.pdf" in SHARED_DOWNLOAD_INTERNAL_PATH
    # Link will be "http://localhost:8081/downloads/report.pdf"
    # aiohttp needs to serve SHARED_DOWNLOAD_INTERNAL_PATH at the prefix /downloads

    # Extract path component from DOWNLOAD_BASE_URL if it has one
    from urllib.parse import urlparse
    parsed_base_url = urlparse(DOWNLOAD_BASE_URL)
    http_server_route_prefix = parsed_base_url.path.rstrip('/')
    if not http_server_route_prefix:  # If base URL is just http://host:port
        http_server_route_prefix = '/'  # Serve from root, this is unlikely desired for downloads
        # Better to enforce a path like /downloads in DOWNLOAD_BASE_URL

    if http_server_route_prefix == '/':
        logger.warning("DOWNLOAD_BASE_URL does not specify a path prefix (e.g., /downloads). "
                       "Serving files from HTTP server root. This might not be ideal.")

    # Example: DOWNLOAD_BASE_URL = "http://localhost:8081/some/prefix"
    # http_server_route_prefix will be "/some/prefix"
    # Files will be served from SHARED_DOWNLOAD_INTERNAL_PATH at this prefix.
    # So, SHARED_DOWNLOAD_INTERNAL_PATH/file.txt will be accessible at http://localhost:8081/some/prefix/file.txt
    http_app.router.add_static(http_server_route_prefix if http_server_route_prefix != "/" else "/",
                               SHARED_DOWNLOAD_INTERNAL_PATH,
                               show_index=True,  # For debugging, can be False
                               follow_symlinks=True)  # Be cautious with symlinks

    app_runner = web.AppRunner(http_app)

    # Start HTTP server as a background task
    http_server_task = asyncio.create_task(start_http_server(app_runner))

    try:
        # Run the MCP server using stdin/stdout streams
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-pandoc",
                    server_version="0.2.0",  # Version bump
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        # Cleanup HTTP server
        await cleanup_http_server(app_runner)
        if http_server_task:
            http_server_task.cancel()  # Request cancellation
            try:
                await http_server_task  # Wait for task to finish (or raise CancelledError)
            except asyncio.CancelledError:
                logger.info("HTTP server task cancelled.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP Pandoc server shutting down...")
