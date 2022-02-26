# Optimus
This utility is the second part of a 3-part management tool I called **Optimus**.

The purpose of Optimus is to streamline the logging and retrieval of submittals' and RFIs' (Request For Information) information.

Part 1: [Optimus NewForma Procore Log](https://github.com/antoine-carpentier/Optimus-NewForma-Procore-Log)  
Part 2: [AWS Optimus I](https://github.com/antoine-carpentier/AWS-Optimus-I)  
Part 3: [AWS Optimus II](https://github.com/antoine-carpentier/AWS-Optimus-II)

## AWS Optimus I

This part of Optimus is responsible for receiving slash commands from Slack, sending instructions to [AWS Optimus II](https://github.com/antoine-carpentier/AWS-Optimus-II) using Amazon SNS and finally sending out an HTTP200 response back to Slack.  
The reason for sending instructions to [AWS Optimus II](https://github.com/antoine-carpentier/AWS-Optimus-II) in lieu of processing the slash commands itself is because of a Slack slash command as a timeout of 3000ms, after which the command is considered failed.  
Due to the time it can take for Optimus to fetch and filter data from a Google Sheets spreadsheet often exceeding this 3000ms response window, it is necessary to send the HTTP200 response before the command is processed.
Using Amazon SNS allows this multithreading to happen. 
