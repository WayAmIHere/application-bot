import discord
from discord.ext import commands
from discord.ui import Button, View
from dotenv import load_dotenv
import os
import asyncio
from typing import Dict, Set

# Load environment variables from .env file
load_dotenv()

# Fetch token and channel IDs from .env
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
QUESTIONS_CHANNEL_ID = int(os.getenv("QUESTIONS_CHANNEL_ID"))
FORUM_CHANNEL_ID = int(os.getenv("FORUM_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Store active applications and their states
active_applications: Dict[int, Set[int]] = {}  # channel_id: set of user_ids
active_channels: Dict[str, discord.TextChannel] = {}  # user_name: channel

class StartButton(View):
    def __init__(self, channel, user):
        super().__init__(timeout=None)
        self.channel = channel
        self.user = user
        self.questions = []
        self.responses = {}
        self.started = False

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple, custom_id="start_button")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.started:
            error_embed = discord.Embed(
                title="Error",
                description="Application already in progress!",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        try:
            self.started = True
            questions_channel = await client.fetch_channel(QUESTIONS_CHANNEL_ID)

            self.questions = []
            async for message in questions_channel.history(limit=100):
                if message.content.strip():
                    self.questions.append(message.content)

            if not self.questions:
                error_embed = discord.Embed(
                    title="Error",
                    description="No questions found. Please contact an administrator.",
                    color=discord.Color.purple()
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return

            self.questions.reverse()
            await interaction.response.defer()

            for i, question in enumerate(self.questions, start=1):
                question_embed = discord.Embed(
                    title=f"Question {i}",
                    description=question,
                    color=discord.Color.purple()
                )
                await interaction.channel.send(embed=question_embed)

                def check(m):
                    return m.author == interaction.user and m.channel == interaction.channel

                try:
                    reminder_sent = False
                    while True:
                        try:
                            user_response = await client.wait_for(
                                "message",
                                timeout=60.0 if not reminder_sent else None,
                                check=check
                            )
                            break
                        except asyncio.TimeoutError:
                            if not reminder_sent:
                                reminder_embed = discord.Embed(
                                    title="Reminder",
                                    description="Please type something to continue.",
                                    color=discord.Color.purple()
                                )
                                await interaction.followup.send(embed=reminder_embed, ephemeral=True)
                                reminder_sent = True
                            continue

                except Exception as e:
                    error_embed = discord.Embed(
                        title="Error",
                        description="An error occurred. Please try again.",
                        color=discord.Color.purple()
                    )
                    await interaction.channel.send(embed=error_embed)
                    return

            completion_embed = discord.Embed(
                title="Application Complete",
                description="You have answered all the questions. Click the **Submit** button below to submit your application.",
                color=discord.Color.purple()
            )
            submit_view = SubmitButton(self.questions, self.responses, self.user, self.channel)
            await interaction.channel.send(embed=completion_embed, view=submit_view)

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description="An error occurred. Please try again.",
                color=discord.Color.purple()
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            self.started = False

    @discord.ui.button(label="View All Questions", style=discord.ButtonStyle.grey, custom_id="view_all_questions_button")
    async def view_all_questions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            questions_channel = await client.fetch_channel(QUESTIONS_CHANNEL_ID)

            questions = []
            async for message in questions_channel.history(limit=100):
                if message.content.strip():
                    questions.append(message.content)

            if not questions:
                error_embed = discord.Embed(
                    title="Error",
                    description="No questions found. Please contact an administrator.",
                    color=discord.Color.purple()
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return

            questions.reverse()
            all_questions_embed = discord.Embed(
                title="All Application Questions",
                color=discord.Color.purple()
            )

            for i, question in enumerate(questions, start=1):
                all_questions_embed.add_field(
                    name=f"Question {i}",
                    value=question,
                    inline=False
                )

            await interaction.response.send_message(embed=all_questions_embed, ephemeral=True)

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description="An error occurred while fetching the questions. Please try again.",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

class SubmitButton(View):
    def __init__(self, questions, responses, user, channel):
        super().__init__(timeout=None)
        self.questions = questions
        self.responses = responses
        self.user = user
        self.channel = channel

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green, custom_id="submit_button")
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            forum_channel = await client.fetch_channel(FORUM_CHANNEL_ID)

            # Fetch messages from the channel
            messages = []
            async for message in self.channel.history(limit=100):
                if message.author == interaction.user:
                    messages.append(message.content)

            submission_embed = discord.Embed(
                title=f"Application Submission by {self.user.name}",
                color=discord.Color.purple()
            )

            for i, message in enumerate(messages, start=1):
                submission_embed.add_field(
                    name=f"Response {i}",
                    value=message,
                    inline=False
                )

            thread = await forum_channel.create_thread(
                name=f"Application by {self.user.name}",
                embed=submission_embed
            )

            guild = interaction.guild
            member_role = discord.utils.get(guild.roles, name="member")
            if member_role:
                await self.channel.set_permissions(member_role, read_messages=True)

            confirmation_embed = discord.Embed(
                title="Application Submitted",
                description=f"Your application has been submitted. The Quantum team is looking into your application.",
                color=discord.Color.purple()
            )
            await self.channel.send(embed=confirmation_embed)

            # Clean up application state
            if self.channel.id in active_applications:
                active_applications[self.channel.id].remove(self.user.id)
                if not active_applications[self.channel.id]:
                    del active_applications[self.channel.id]
            if self.user.name in active_channels:
                del active_channels[self.user.name]

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description="An error occurred while submitting your application. Please try again.",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

class ApplyButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.green, custom_id="apply_button")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.user
            guild = interaction.guild

            # Check if user already has an active application
            for channel_id, users in active_applications.items():
                if user.id in users:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        error_embed = discord.Embed(
                            title="Active Application",
                            description=f"You already have an active application in {channel.mention}",
                            color=discord.Color.purple()
                        )
                        await interaction.response.send_message(embed=error_embed, ephemeral=True)
                        return

            channel_name = f"application-{user.name.lower()}"

            member_role = discord.utils.get(guild.roles, name="member")
            if not member_role:
                error_embed = discord.Embed(
                    title="Error",
                    description="The 'member' role does not exist. Please contact an administrator.",
                    color=discord.Color.purple()
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return

            apply_category = discord.utils.get(guild.categories, name="Apply")
            if not apply_category:
                error_embed = discord.Embed(
                    title="Error",
                    description="The 'Apply' category does not exist. Please contact an administrator.",
                    color=discord.Color.purple()
                )
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True),
                member_role: discord.PermissionOverwrite(read_messages=False)
            }

            new_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=apply_category
            )

            # Store application state
            active_applications[new_channel.id] = {user.id}
            active_channels[user.name] = new_channel

            # Create welcome embed with cleanup warning
            welcome_embed = discord.Embed(
                title="Welcome!",
                description=f"Hello {user.mention}, welcome to your application channel!",
                color=discord.Color.purple()
            )
            welcome_embed.add_field(
                name="Instructions",
                value="Click the Start button below to begin your application.",
                inline=False
            )
            welcome_embed.add_field(
                name="⚠️ Important",
                value="**This channel will automatically close in 1 minute if you don't start the application.**",
                inline=False
            )
            welcome_embed.set_footer(text="Click 'Start' to begin your application process")

            start_view = StartButton(new_channel, user)
            await new_channel.send(embed=welcome_embed, view=start_view)

            channel_created_embed = discord.Embed(
                title="Channel Created",
                description=f"Created a new channel for you: {new_channel.mention}",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=channel_created_embed, ephemeral=True)

            # Start channel cleanup countdown
            await self.start_countdown(new_channel, user)

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description="An error occurred while processing your request. Please try again.",
                color=discord.Color.purple()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    async def start_countdown(self, channel, user):
        try:
            await asyncio.sleep(60)

            # Check if the application is still active and not started
            if channel.id in active_applications and user.id in active_applications[channel.id]:
                async for message in channel.history(limit=100):
                    if message.author == client.user and isinstance(message.embeds[0], discord.Embed):
                        if message.embeds[0].title == "Application Complete":
                            return  # Application is in progress, don't delete channel

                # Clean up application state
                active_applications[channel.id].remove(user.id)
                if not active_applications[channel.id]:
                    del active_applications[channel.id]
                if user.name in active_channels:
                    del active_channels[user.name]

                await channel.delete()
        except discord.NotFound:
            pass  # Channel already deleted
        except Exception as e:
            pass  # Silently handle other errors during cleanup

@client.event
async def on_ready():
    try:
        channel = await client.fetch_channel(CHANNEL_ID)

        # Clear existing messages
        async for message in channel.history(limit=100):
            await message.delete()

        embed = discord.Embed(
            title="Apply",
            description="Click the button below to start your application.",
            color=discord.Color.purple()
        )

        view = ApplyButton()
        await channel.send(embed=embed, view=view)

    except Exception as e:
        pass

client.run(TOKEN)
